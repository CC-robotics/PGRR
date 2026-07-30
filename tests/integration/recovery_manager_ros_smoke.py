#!/usr/bin/env python3
"""Verify real Nav2 action preemption and original-goal restoration."""

from __future__ import annotations

import time

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
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
        print(
            "PASS recovery manager ROS smoke: "
            f"temporary={temporary}, restored={restored}, decisions={len(driver.decisions)}"
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
