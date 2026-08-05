#!/usr/bin/env python3
"""Verify real Nav2 action preemption and original-goal restoration."""

from __future__ import annotations

import math
import time

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
)
from ramp_core.recovery.safety import EmergencyEscapeMode
from ramp_core.state_machine import RecoveryState, StateTransition
from ramp_core.types import PlannerStatus, Pose2D
from ramp_msgs.msg import FailureStatus, RecoveryDecision
from ramp_ros.nodes.recovery_manager_node import RecoveryManagerNode
from rclpy.action import ActionServer
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class RecoveryDriver(Node):
    def __init__(self) -> None:
        super().__init__("recovery_manager_smoke_driver")
        self.goals: list[tuple[float, float]] = []
        self.decisions: list[RecoveryDecision] = []
        self.action_server = ActionServer(self, NavigateToPose, "/navigate_to_pose", self._execute)
        self.scan_publisher = self.create_publisher(LaserScan, "/scan", qos_profile_sensor_data)
        self.odom_publisher = self.create_publisher(Odometry, "/odom", qos_profile_sensor_data)
        self.failure_publisher = self.create_publisher(FailureStatus, "/failure_status", 10)
        self.status_publisher = self.create_publisher(
            GoalStatusArray, "/navigate_to_pose/_action/status", 10
        )
        self.subscription = self.create_subscription(
            RecoveryDecision, "/recovery_decision", self.decisions.append, 10
        )

    def _execute(self, goal_handle: object) -> NavigateToPose.Result:
        request = goal_handle.request  # type: ignore[attr-defined]
        self.goals.append((request.pose.pose.position.x, request.pose.pose.position.y))
        goal_handle.succeed()  # type: ignore[attr-defined]
        return NavigateToPose.Result()

    def publish_inputs(self, index: int) -> None:
        scan = LaserScan()
        scan.header.stamp.sec = index
        scan.angle_min = -3.141592653589793
        scan.angle_increment = 2.0 * 3.141592653589793 / 360.0
        scan.range_min = 0.05
        scan.range_max = 10.0
        # Forward clearance remains above the close-hazard backup threshold,
        # while the left side is distinctly clearer, so collision recovery
        # should exercise a legal temporary subgoal and subsequent REJOIN.
        scan.ranges = [2.0] * 180 + [4.0] * 180
        odometry = Odometry()
        odometry.header.stamp.sec = index
        odometry.pose.pose.position.x = 0.0 if index == 1 else 0.10
        failure = FailureStatus()
        # Keep the trigger high until the manager has issued its first
        # temporary goal, then clear it so this smoke test exercises REJOIN
        # instead of the persistent-failure escalation path.
        if index >= 3 and not self.goals:
            failure.collision_risk = 0.8
            failure.failure_score = 0.8
            failure.triggered = True
        status = GoalStatusArray()
        item = GoalStatus()
        item.status = GoalStatus.STATUS_EXECUTING
        status.status_list.append(item)
        self.scan_publisher.publish(scan)
        self.odom_publisher.publish(odometry)
        self.failure_publisher.publish(failure)
        self.status_publisher.publish(status)


def _assert_terminal_publication(
    manager: RecoveryManagerNode,
    driver: RecoveryDriver,
    executor: SingleThreadedExecutor,
    *,
    current: RecoveryState,
    expected_state: int,
    reason: str,
) -> None:
    start = len(driver.decisions)
    manager._machine.state = current
    manager._published_emergency_mode = EmergencyEscapeMode.BACKUP
    transition = StateTransition(
        previous=RecoveryState.EMERGENCY_STOP,
        current=current,
        changed=True,
        reason=reason,
    )
    if not manager._publish_terminal_transition(transition, 1.0):
        raise RuntimeError(f"terminal transition was not published: {transition}")
    if manager._published_emergency_mode is not None:
        raise RuntimeError("terminal publication retained stale emergency mode")

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.05)
        matches = [item for item in driver.decisions[start:] if item.reason == reason]
        if matches:
            decision = matches[-1]
            if int(decision.recovery_state) != expected_state:
                raise RuntimeError(
                    f"terminal state mismatch for {reason}: {decision.recovery_state}"
                )
            return
    raise RuntimeError(
        f"terminal decision was not received: reason={reason}, "
        f"decisions={[(item.recovery_state, item.reason) for item in driver.decisions[start:]]}"
    )


def _assert_emergency_rotation_bounds(manager: RecoveryManagerNode) -> None:
    expected_clearance = max(
        manager._float("emergency_rotation_clearance_m"),
        manager._float("footprint_stop_clearance_m")
        + manager._float("emergency_release_hysteresis_m"),
    )
    controller = manager._emergency_escape
    if not math.isclose(controller.rotation_clearance_m, expected_clearance):
        raise RuntimeError(
            "emergency rotation omitted the footprint release margin: "
            f"expected={expected_clearance}, observed={controller.rotation_clearance_m}"
        )
    if not math.isclose(controller.turn_duration_s, 0.8):
        raise RuntimeError(f"unexpected emergency turn duration: {controller.turn_duration_s}")
    if controller.maximum_turn_pulses != 4:
        raise RuntimeError(
            f"unexpected emergency turn pulse budget: {controller.maximum_turn_pulses}"
        )


def _assert_recurrent_escape_mask(manager: RecoveryManagerNode) -> None:
    threshold = manager._integer("bc_recurrent_escape_after_recoveries")
    if threshold != 1:
        raise RuntimeError(f"unexpected BC recurrent escape threshold: {threshold}")
    minimum_lateral_m = manager._float("recurrent_escape_minimum_lateral_displacement_m")
    pose = Pose2D(0.0, 0.0, 0.0)
    path_heading_rad = 0.0
    lateral_ids = [
        action.action_id
        for action in ACTIONS[:WAIT_ACTION_ID]
        if (
            (target := action.target_pose(pose)) is not None
            and abs(target.y - pose.y) >= minimum_lateral_m - 1.0e-9
        )
    ]
    straight_id = next(
        action.action_id for action in ACTIONS[:WAIT_ACTION_ID] if action.angle_degrees == 0
    )
    legal_lateral, illegal_lateral = lateral_ids[:2]
    ordinary = np.zeros(ACTION_COUNT, dtype=np.bool_)
    ordinary[[legal_lateral, straight_id, WAIT_ACTION_ID, BACKUP_ACTION_ID]] = True
    ordinary[[REPLAN_ACTION_ID, CONTINUE_ACTION_ID]] = True

    # A first recovery for freeze/oscillation must retain the ordinary mask;
    # only an observable directional-yield latch authorizes this escalation.
    manager._machine._consecutive_recoveries = threshold
    manager._bc_yield_latch.reset()
    unlatched = manager._constrain_bc_recurrent_escape(
        ordinary,
        pose=pose,
        path_heading_rad=path_heading_rad,
    )
    if not np.array_equal(unlatched, ordinary):
        raise RuntimeError("recurrent escape changed an unlatched first-recovery mask")
    if manager._bc_recurrent_escape_telemetry(
        ordinary,
        unlatched,
        pose=pose,
        path_heading_rad=path_heading_rad,
    ):
        raise RuntimeError("recurrent escape emitted telemetry without a directional yield")

    manager._bc_yield_latch.update(
        collision_risk=manager._machine.config.tau_on,
        forward_clearance_m=0.5,
    )
    if not manager._bc_yield_latch.latched:
        raise RuntimeError("directional-yield latch did not activate for first recovery")
    constrained = manager._constrain_bc_recurrent_escape(
        ordinary,
        pose=pose,
        path_heading_rad=path_heading_rad,
    )
    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[[legal_lateral, REPLAN_ACTION_ID]] = True
    if not np.array_equal(constrained, expected):
        raise RuntimeError(
            f"recurrent escape mask mismatch: expected={expected}, observed={constrained}"
        )
    if bool(constrained[illegal_lateral]) or bool(np.any(constrained & ~ordinary)):
        raise RuntimeError("recurrent escape unmasked a planning-invalid action")
    telemetry = manager._bc_recurrent_escape_telemetry(
        ordinary,
        constrained,
        pose=pose,
        path_heading_rad=path_heading_rad,
    )
    if "bc_recurrent_escape=applied" not in telemetry or f"count={threshold}" not in telemetry:
        raise RuntimeError(f"recurrent escape telemetry mismatch: {telemetry}")
    if "pre=" not in telemetry or "final=" not in telemetry:
        raise RuntimeError(f"recurrent escape telemetry omitted masks: {telemetry}")
    if "minimum_lateral_m=0.250" not in telemetry or "lateral_ids=" not in telemetry:
        raise RuntimeError(f"recurrent escape telemetry omitted path-frame evidence: {telemetry}")

    safe_fallback = np.zeros(ACTION_COUNT, dtype=np.bool_)
    safe_fallback[[WAIT_ACTION_ID, BACKUP_ACTION_ID, CONTINUE_ACTION_ID]] = True
    observed_fallback = manager._constrain_bc_recurrent_escape(
        safe_fallback,
        pose=pose,
        path_heading_rad=path_heading_rad,
    )
    if not np.array_equal(observed_fallback, safe_fallback):
        raise RuntimeError("recurrent escape discarded the original safe fallback mask")
    fallback_telemetry = manager._bc_recurrent_escape_telemetry(
        safe_fallback,
        observed_fallback,
        pose=pose,
        path_heading_rad=path_heading_rad,
    )
    if "bc_recurrent_escape=unavailable" not in fallback_telemetry:
        raise RuntimeError(f"recurrent escape fallback telemetry mismatch: {fallback_telemetry}")

    rotated_pose = Pose2D(0.0, 0.0, math.pi / 2.0)
    rotated = np.zeros(ACTION_COUNT, dtype=np.bool_)
    # Action 3 is robot-frame straight but path-lateral when facing north.
    # Action 0 has a non-zero robot-frame angle but points along the eastbound path.
    rotated[[0, 3, WAIT_ACTION_ID]] = True
    rotated_constrained = manager._constrain_bc_recurrent_escape(
        rotated,
        pose=rotated_pose,
        path_heading_rad=0.0,
    )
    rotated_expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    rotated_expected[3] = True
    if not np.array_equal(rotated_constrained, rotated_expected):
        raise RuntimeError(
            "rotated path-frame recurrent escape mismatch: "
            f"expected={rotated_expected}, observed={rotated_constrained}"
        )
    manager._bc_yield_latch.reset()


def _assert_bc_subgoal_lifecycle(manager: RecoveryManagerNode) -> None:
    option = manager._bc_subgoal_option
    if abs(option.earliest_completion_s - 3.0) > 1.0e-9:
        raise RuntimeError(
            f"BC subgoal earliest completion mismatch: {option.earliest_completion_s}"
        )
    if abs(option.maximum_duration_s - 6.0) > 1.0e-9:
        raise RuntimeError(f"BC subgoal hard limit mismatch: {option.maximum_duration_s}")
    if option.maximum_duration_s >= manager._machine.config.maximum_recovery_duration_s:
        raise RuntimeError("BC subgoal hard limit does not precede recovery timeout")

    policy_type = manager._policy_type
    active_action = manager._active_action
    action_started_s = manager._action_started_s
    adapter_status = manager._adapter._status
    try:
        manager._policy_type = "bc"
        manager._active_action = 3
        manager._action_started_s = 10.0
        manager._adapter._status = PlannerStatus.SUCCEEDED
        if manager._action_complete(12.999):
            raise RuntimeError("successful BC subgoal completed before settle plus execution")
        if not manager._action_complete(13.0):
            raise RuntimeError("successful BC subgoal did not complete at its earliest boundary")
        manager._adapter._status = PlannerStatus.ACTIVE
        if manager._action_complete(15.999):
            raise RuntimeError("active BC subgoal completed before its hard limit")
        if not manager._action_complete(16.0):
            raise RuntimeError("active BC subgoal did not complete at its hard limit")

        # The lifecycle bound applies only to learned subgoals. Preserve the
        # existing WAIT duration and planner-result completion used by the
        # heuristic subgoal policy.
        manager._active_action = WAIT_ACTION_ID
        manager._action_started_s = 20.0
        if manager._action_complete(20.499) or not manager._action_complete(20.5):
            raise RuntimeError("BC subgoal timing changed the WAIT completion boundary")
        manager._policy_type = "heuristic"
        manager._active_action = 3
        manager._action_started_s = 30.0
        manager._adapter._status = PlannerStatus.SUCCEEDED
        if not manager._action_complete(30.0):
            raise RuntimeError("BC subgoal timing changed heuristic planner completion")
    finally:
        manager._policy_type = policy_type
        manager._active_action = active_action
        manager._action_started_s = action_started_s
        manager._adapter._status = adapter_status


def _assert_directional_yield_lifecycle(manager: RecoveryManagerNode) -> None:
    latch = manager._bc_yield_latch
    latch.reset()
    if abs(latch.release_clearance_m - 1.25) > 1.0e-9 or latch.release_frames != 3:
        raise RuntimeError(
            "unexpected directional-yield configuration: "
            f"clearance={latch.release_clearance_m}, frames={latch.release_frames}"
        )
    clearance = manager._task_forward_clearance(Pose2D(0.1, 0.0, 0.0))
    if clearance is None or abs(clearance - 2.0) > 1.0e-6:
        raise RuntimeError(f"task-forward clearance sector mismatch: {clearance}")
    if not latch.update(collision_risk=0.8, forward_clearance_m=clearance, observation_id=1):
        raise RuntimeError("collision warning did not latch directional yield")
    for observation_id in range(2, latch.release_frames + 1):
        if not latch.update(
            collision_risk=0.0,
            forward_clearance_m=clearance,
            observation_id=observation_id,
        ):
            raise RuntimeError("directional yield released without consecutive evidence")
    if latch.update(
        collision_risk=0.0,
        forward_clearance_m=clearance,
        observation_id=latch.release_frames + 1,
    ):
        raise RuntimeError("directional yield did not release at its evidence boundary")


def _assert_recurrent_path_envelope(manager: RecoveryManagerNode) -> None:
    policy_type = manager._policy_type
    recovery_count = manager._machine._consecutive_recoveries
    latch = manager._bc_yield_latch
    latched = latch.latched
    clear_frames = latch.clear_frames
    observation_id = latch.last_observation_id
    try:
        manager._policy_type = "bc"
        latch.latched = False
        latch.clear_frames = 0
        manager._machine._consecutive_recoveries = 1
        if abs(manager._effective_recovery_path_deviation() - 0.6) > 1.0e-9:
            raise RuntimeError("unlatched BC unexpectedly used recurrent path envelope")
        latch.latched = True
        manager._machine._consecutive_recoveries = 0
        if abs(manager._effective_recovery_path_deviation() - 0.6) > 1.0e-9:
            raise RuntimeError("first BC attempt unexpectedly used recurrent path envelope")
        manager._machine._consecutive_recoveries = 1
        if abs(manager._effective_recovery_path_deviation() - 1.5) > 1.0e-9:
            raise RuntimeError("latched recurrent BC did not use wider path envelope")
        manager._policy_type = "expert"
        if abs(manager._effective_recovery_path_deviation() - 0.6) > 1.0e-9:
            raise RuntimeError("expert unexpectedly used learned recurrent path envelope")
    finally:
        manager._policy_type = policy_type
        manager._machine._consecutive_recoveries = recovery_count
        latch.latched = latched
        latch.clear_frames = clear_frames
        latch.last_observation_id = observation_id


def main() -> int:
    rclpy.init(
        args=[
            "--ros-args",
            "-p",
            "goal_x:=5.0",
            "-p",
            "frames_on:=1",
            "-p",
            "minimum_action_hold_s:=0.1",
            "-p",
            "decision_frequency_hz:=10.0",
        ]
    )
    driver = RecoveryDriver()
    manager = RecoveryManagerNode()
    executor = SingleThreadedExecutor()
    executor.add_node(driver)
    executor.add_node(manager)
    try:
        deadline = time.monotonic() + 10.0
        index = 1
        while time.monotonic() < deadline and len(driver.goals) < 2:
            driver.publish_inputs(index)
            index += 1
            for _ in range(4):
                executor.spin_once(timeout_sec=0.05)
        if len(driver.goals) < 2:
            raise RuntimeError(
                f"expected temporary and restored goals, observed {driver.goals}; "
                f"decisions={[(item.action_id, item.reason) for item in driver.decisions]}"
            )
        temporary, restored = driver.goals[:2]
        if abs(temporary[0] - 5.0) < 1.0e-3 and abs(temporary[1]) < 1.0e-3:
            raise RuntimeError(f"first goal was not temporary: {temporary}")
        if abs(restored[0] - 5.0) > 1.0e-3 or abs(restored[1]) > 1.0e-3:
            raise RuntimeError(f"original goal was not restored: {restored}")
        if not any(item.has_temporary_goal for item in driver.decisions):
            raise RuntimeError("manager published no temporary-goal recovery decision")
        _assert_emergency_rotation_bounds(manager)
        _assert_recurrent_escape_mask(manager)
        _assert_bc_subgoal_lifecycle(manager)
        _assert_directional_yield_lifecycle(manager)
        _assert_recurrent_path_envelope(manager)
        nonterminal = StateTransition(
            previous=RecoveryState.EMERGENCY_STOP,
            current=RecoveryState.NORMAL,
            changed=True,
            reason="safety_clear",
        )
        if manager._publish_terminal_transition(nonterminal, 1.0):
            raise RuntimeError("nonterminal transition was consumed by terminal publisher")
        _assert_terminal_publication(
            manager,
            driver,
            executor,
            current=RecoveryState.FAILED,
            expected_state=RecoveryDecision.FAILED,
            reason="recovery_sequence_timeout",
        )
        _assert_terminal_publication(
            manager,
            driver,
            executor,
            current=RecoveryState.SUCCEEDED,
            expected_state=RecoveryDecision.SUCCEEDED,
            reason="goal_reached",
        )
        print(
            "PASS recovery manager ROS smoke: "
            f"temporary={temporary}, restored={restored}, decisions={len(driver.decisions)}, "
            "bc_subgoal=bounded, emergency_turn=bounded, directional_yield=observable, "
            "recurrent_escape=planning_safe, recurrent_path=bounded, "
            "terminal_reasons=preserved"
        )
        return 0
    finally:
        executor.remove_node(manager)
        executor.remove_node(driver)
        manager.destroy_node()
        driver.action_server.destroy()
        driver.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
