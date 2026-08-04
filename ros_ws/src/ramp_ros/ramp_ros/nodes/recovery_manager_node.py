"""Failure-triggered heuristic recovery manager for Nav2 temporary goals."""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import PoseArray, PoseStamped, Twist
from nav_msgs.msg import OccupancyGrid as OccupancyGridMessage
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMessage
from ramp_core.action_mask import (
    ActionMaskConfig,
    apply_observable_scan_mask,
    apply_path_corridor_mask,
    compute_action_mask,
    path_corridor_target_is_permitted,
)
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
    RecoveryActionKind,
)
from ramp_core.kinematics import stopping_distance
from ramp_core.observations import (
    HumanState,
    PrivilegedState,
    RecoveryObservation,
    navigation_path_or_goal,
    select_local_path_waypoints,
)
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.expert import PlanningRecoveryExpert, update_expert_history
from ramp_core.planning.online import (
    augment_grid_with_scan,
    directional_scan_clearance,
    estimate_human_states,
    privileged_time_to_collision,
    sanitize_near_field_returns,
    scan_segment_is_free,
)
from ramp_core.recovery.heuristic import HeuristicRecoveryConfig, HeuristicRecoveryPolicy
from ramp_core.recovery.options import (
    BoundedBackupOption,
    PrivilegedYieldOption,
    constrain_recurrent_yield_escape,
    constrain_rejoin_actions,
    constrain_repeated_backup,
    constrain_repeated_replan,
    constrain_stalled_rejoin,
    constrain_stalled_wait,
    should_continue_recovery_option,
)
from ramp_core.recovery.safety import (
    EmergencyEscapeController,
    EmergencyEscapeMode,
    backup_increases_obstacle_clearance,
    collision_latched_motion_clearance,
    emergency_hazard_with_hysteresis,
    emergency_mode_reason,
    update_collision_safety_latch,
)
from ramp_core.state_machine import (
    RecoveryState,
    RecoveryStateMachine,
    RecoveryStateMachineConfig,
    StateMachineInput,
)
from ramp_core.types import (
    FailurePrediction,
    PlannerStatus,
    Pose2D,
    Velocity2D,
    select_planner_status,
)
from ramp_core.types import (
    RecoveryDecision as CoreRecoveryDecision,
)
from ramp_ml.inference import ONNXRecoveryPolicy
from ramp_msgs.msg import FailureStatus, RecoveryDecision
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

from ramp_ros.adapters.nav2_adapter import Nav2Adapter

STATE_IDS = {state: index for index, state in enumerate(RecoveryState)}


def _yaw_from_odometry(message: Odometry) -> float:
    q = message.pose.pose.orientation
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _planner_status(value: int) -> PlannerStatus:
    return {
        GoalStatus.STATUS_ACCEPTED: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_EXECUTING: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_SUCCEEDED: PlannerStatus.SUCCEEDED,
        GoalStatus.STATUS_ABORTED: PlannerStatus.ABORTED,
        GoalStatus.STATUS_CANCELED: PlannerStatus.CANCELED,
        GoalStatus.STATUS_CANCELING: PlannerStatus.CANCELED,
    }.get(value, PlannerStatus.UNKNOWN)


class RecoveryManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("recovery_manager")
        self._declare_parameters()
        self._policy_type = str(self.get_parameter("policy_type").value)
        if self._policy_type not in {"heuristic", "expert", "bc"}:
            raise ValueError("policy_type must be heuristic, expert, or bc")
        if (
            not 0.0
            < self._float("oracle_trigger_intervention_horizon_s")
            <= self._float("oracle_trigger_horizon_s")
        ):
            raise ValueError("Oracle intervention horizon must lie inside prediction horizon")
        self._goal = Pose2D(self._float("goal_x"), self._float("goal_y"), self._float("goal_yaw"))
        self._start = Pose2D(
            self._float("robot_start_x"),
            self._float("robot_start_y"),
            self._float("robot_start_yaw"),
        )
        state_config = RecoveryStateMachineConfig(
            tau_on=self._float("tau_on"),
            tau_off=self._float("tau_off"),
            frames_on=self._integer("frames_on"),
            frames_off=self._integer("frames_off"),
            cooldown_s=self._float("cooldown_s"),
            minimum_action_hold_s=self._float("minimum_action_hold_s"),
            maximum_recovery_duration_s=self._float("maximum_recovery_duration_s"),
            maximum_extended_recovery_duration_s=self._float(
                "maximum_extended_recovery_duration_s"
            ),
            maximum_rejoin_duration_s=self._float("maximum_rejoin_duration_s"),
            maximum_rejoin_retries_per_sequence=self._integer(
                "maximum_rejoin_retries_per_sequence"
            ),
            maximum_consecutive_recoveries=self._integer("maximum_consecutive_recoveries"),
        )
        self._machine = RecoveryStateMachine(state_config)
        self._machine.set_original_goal(self._goal)
        self._backup_option = BoundedBackupOption(
            minimum_duration_s=self._float("backup_minimum_duration_s"),
            maximum_duration_s=self._float("backup_maximum_duration_s"),
            speed_mps=self._float("backup_speed_mps"),
            clearance_improvement_m=self._float("backup_clearance_improvement_m"),
            mask_validated_distance_m=self._float("backup_mask_validated_distance_m"),
        )
        if self._policy_type == "bc":
            self._policy = ONNXRecoveryPolicy(
                str(self.get_parameter("model_path").value),
                lidar_max_m=self._float("model_lidar_max_m"),
                execution_provider=str(self.get_parameter("onnx_execution_provider").value),
            )
        else:
            self._policy = HeuristicRecoveryPolicy(
                HeuristicRecoveryConfig(
                    side_clearance_ratio=self._float("side_clearance_ratio"),
                    collision_wait_clearance_m=self._float("collision_wait_clearance_m"),
                    collision_close_clearance_m=self._float("collision_close_clearance_m"),
                    collision_emergency_wait_clearance_m=self._float(
                        "collision_emergency_wait_clearance_m"
                    ),
                    preferred_subgoal_radius_m=self._float("preferred_subgoal_radius_m"),
                    minimum_subgoal_progress_m=self._float("minimum_subgoal_progress_m"),
                    path_alignment_weight=self._float("path_alignment_weight"),
                    goal_alignment_weight=self._float("goal_alignment_weight"),
                    progress_reward_weight=self._float("progress_reward_weight"),
                    clearance_reward_weight=self._float("clearance_reward_weight"),
                    radius_preference_weight=self._float("radius_preference_weight"),
                    lidar_field_of_view_degrees=self._float("lidar_field_of_view_degrees"),
                    side_cooldown_decisions=self._integer("side_cooldown_decisions"),
                    collision_max_backup_decisions=self._integer("collision_max_backup_decisions"),
                    freeze_subgoal_after_decisions=self._integer("freeze_subgoal_after_decisions"),
                    freeze_max_backup_decisions=self._integer("freeze_max_backup_decisions"),
                    deadlock_backup_after_decisions=self._integer(
                        "deadlock_backup_after_decisions"
                    ),
                    deadlock_replan_after_decisions=self._integer(
                        "deadlock_replan_after_decisions"
                    ),
                )
            )
        self._adapter = Nav2Adapter(
            self,
            str(self.get_parameter("navigate_to_pose_action").value),
            str(self.get_parameter("map_frame").value),
        )
        self._adapter.remember_navigation_goal(self._goal)
        self._odom: Odometry | None = None
        self._scan: LaserScan | None = None
        self._lidar_stack: deque[np.ndarray[Any, np.dtype[np.float32]]] = deque(maxlen=5)
        self._path: tuple[tuple[float, float], ...] = ()
        self._task_corridor_path: tuple[tuple[float, float], ...] = ()
        self._map: OccupancyGrid | None = None
        self._privileged_humans: tuple[HumanState, ...] = ()
        self._previous_human_positions: tuple[tuple[float, float], ...] = ()
        self._previous_human_timestamp_s: float | None = None
        self._received_privileged_humans = False
        self._oracle_yield = PrivilegedYieldOption(
            task_heading_rad=math.atan2(
                self._goal.y - self._start.y,
                self._goal.x - self._start.x,
            ),
            passed_margin_m=self._float("oracle_yield_passed_margin_m"),
            maximum_retreat_m=self._float("oracle_yield_maximum_retreat_m"),
            recurrence_progress_m=self._float("oracle_yield_recurrence_progress_m"),
            maximum_recurrences_without_progress=self._integer(
                "oracle_yield_maximum_recurrences_without_progress"
            ),
        )
        self._expert_previous_side = 0
        self._expert_repeated_waits = 0
        self._bc_waits_without_progress = 0
        self._bc_backups_without_progress = 0
        self._bc_replans_without_progress = 0
        self._bc_progress_reference_distance_m: float | None = None
        self._failure = FailurePrediction(0.0, 0.0, 0.0, 0.0)
        self._planner_status = PlannerStatus.UNKNOWN
        self._armed = False
        self._armed_at_s = float("inf")
        self._ready_since_s: float | None = None
        self._initial_world_position: tuple[float, float] | None = None
        self._movement_observed = False
        self._base_action = np.zeros(2, dtype=np.float32)
        self._distance_history: deque[float] = deque(maxlen=10)
        self._angular_history: deque[float] = deque(maxlen=10)
        self._active_action = CONTINUE_ACTION_ID
        self._goal_preempted = False
        self._action_started_s = float("-inf")
        self._backup_start_clearance_m: float | None = None
        self._emergency = False
        self._collision_safety_latched = False
        self._emergency_escape_active = False
        self._emergency_escape_mode = EmergencyEscapeMode.STOP
        self._published_emergency_mode: EmergencyEscapeMode | None = None
        self._emergency_escape = EmergencyEscapeController(
            hold_s=self._float("emergency_hold_s"),
            backup_duration_s=self._float("emergency_backup_duration_s"),
            backup_clearance_m=self._float("emergency_backup_clearance_m"),
            release_speed_mps=self._float("emergency_release_speed_mps"),
            rotation_clearance_m=self._float("emergency_rotation_clearance_m"),
            forward_entry_clearance_m=self._float("emergency_forward_entry_clearance_m"),
            backup_reset_clear_s=self._float("emergency_backup_reset_clear_s"),
            minimum_retreat_pulses=self._integer("emergency_minimum_retreat_pulses"),
            maximum_improving_backups=self._integer("emergency_maximum_improving_backups"),
            backup_progress_m=self._float("emergency_backup_progress_m"),
        )
        self._decision_publisher = self.create_publisher(
            RecoveryDecision, str(self.get_parameter("recovery_decision_topic").value), 10
        )
        self._override_publisher = self.create_publisher(
            Twist, str(self.get_parameter("cmd_vel_topic").value), 10
        )
        self._subscription_handles: list[Any] = []
        self._subscribe()
        self._decision_timer = self.create_timer(
            1.0 / self._float("decision_frequency_hz"), self._decision_step
        )
        self._control_timer = self.create_timer(
            1.0 / self._float("control_frequency_hz"), self._control_step
        )

    def _declare_parameters(self) -> None:
        string_defaults = {
            "odom_topic": "odom",
            "scan_topic": "scan",
            "base_cmd_vel_topic": "cmd_vel",
            "cmd_vel_topic": "cmd_vel",
            "global_path_topic": "plan",
            "map_topic": "map",
            "nav_status_topic": "navigate_to_pose/_action/status",
            "failure_status_topic": "failure_status",
            "recovery_decision_topic": "recovery_decision",
            "navigate_to_pose_action": "navigate_to_pose",
            "map_frame": "map",
            "policy_type": "heuristic",
            "privileged_humans_topic": "/ramp/privileged/humans",
            "model_path": "",
            "onnx_execution_provider": "CPUExecutionProvider",
        }
        for name, value in string_defaults.items():
            self.declare_parameter(name, value)
        numeric_defaults: dict[str, float | int] = {
            "goal_x": 0.0,
            "goal_y": 0.0,
            "goal_yaw": 0.0,
            "robot_start_x": 0.0,
            "robot_start_y": 0.0,
            "robot_start_yaw": 0.0,
            "odometry_is_world_frame": False,
            "goal_tolerance_m": 0.25,
            "decision_frequency_hz": 2.0,
            "control_frequency_hz": 10.0,
            "model_lidar_max_m": 6.0,
            "bc_action_interval_s": 0.5,
            "arming_grace_s": 1.0,
            "startup_failure_arm_s": 4.0,
            "tau_on": 0.65,
            "tau_off": 0.35,
            "frames_on": 1,
            "frames_off": 4,
            "cooldown_s": 2.0,
            "minimum_action_hold_s": 0.5,
            "maximum_recovery_duration_s": 8.0,
            "maximum_extended_recovery_duration_s": 30.0,
            "maximum_rejoin_duration_s": 5.0,
            "maximum_rejoin_retries_per_sequence": 2,
            "maximum_consecutive_recoveries": 4,
            "side_clearance_ratio": 1.25,
            "collision_wait_clearance_m": 1.3,
            "collision_close_clearance_m": 0.60,
            "collision_emergency_wait_clearance_m": 0.5,
            "preferred_subgoal_radius_m": 1.0,
            "minimum_subgoal_progress_m": 0.15,
            "path_alignment_weight": 1.0,
            "goal_alignment_weight": 0.5,
            "progress_reward_weight": 0.4,
            "clearance_reward_weight": 0.2,
            "radius_preference_weight": 0.35,
            "lidar_field_of_view_degrees": 270.0,
            "side_cooldown_decisions": 4,
            "collision_max_backup_decisions": 1,
            "freeze_subgoal_after_decisions": 2,
            "freeze_max_backup_decisions": 6,
            "deadlock_backup_after_decisions": 2,
            "deadlock_replan_after_decisions": 4,
            "robot_clearance_m": 0.25,
            "maximum_recovery_path_deviation_m": 0.9,
            "backup_speed_mps": 0.15,
            "backup_minimum_duration_s": 0.8,
            "backup_maximum_duration_s": 3.0,
            "backup_clearance_improvement_m": 0.25,
            "backup_mask_validated_distance_m": 0.45,
            "wait_duration_s": 0.5,
            "subgoal_settle_s": 1.0,
            "expert_replan_interval_s": 0.5,
            "expert_rejoin_block_threshold": 0.9,
            "expert_wait_budget_decisions": 3,
            "bc_rejoin_block_threshold": 0.65,
            "bc_wait_budget_decisions": 3,
            "bc_backup_budget_decisions": 2,
            "bc_replan_budget_decisions": 1,
            "bc_progress_reset_m": 0.25,
            "braking_acceleration_mps2": 0.8,
            "control_latency_s": 0.15,
            "stopping_margin_m": 0.45,
            "footprint_stop_clearance_m": 0.48,
            "collision_latched_stop_clearance_m": 0.60,
            "collision_latched_action_clearance_m": 0.65,
            "footprint_backup_forward_angle_degrees": 80.0,
            "emergency_hold_s": 0.5,
            "emergency_backup_duration_s": 0.8,
            "emergency_backup_clearance_m": 0.70,
            "emergency_release_speed_mps": 0.03,
            "emergency_release_hysteresis_m": 0.05,
            # Jackal's measured half width is smaller than its 0.36 m
            # circumscribed collision radius. This threshold preserves a
            # positive lateral margin while permitting in-place narrow-door
            # alignment instead of a permanent conservative stop.
            "emergency_rotation_clearance_m": 0.24,
            "emergency_forward_entry_clearance_m": 0.65,
            "emergency_backup_reset_clear_s": 3.0,
            "emergency_minimum_retreat_pulses": 3,
            "emergency_turn_speed_radps": 0.6,
            "emergency_forward_speed_mps": 0.12,
            "emergency_translation_clearance_m": 0.36,
            "emergency_maximum_improving_backups": 8,
            "emergency_backup_progress_m": 0.05,
            "minimum_valid_lidar_range_m": 0.0,
            "bilateral_edge_self_return_max_m": 0.34,
            "human_radius_m": 0.35,
            "robot_radius_m": 0.36,
            "maximum_human_speed_mps": 2.0,
            # Store raw occupied endpoints. Robot clearance is applied
            # separately by compute_action_mask; any positive grid-cell
            # inflation here is additive and can erase narrow corridors.
            "expert_scan_inflation_m": 0.0,
            "oracle_trigger_horizon_s": 3.0,
            "oracle_trigger_intervention_horizon_s": 1.5,
            "oracle_trigger_margin_m": 0.25,
            "oracle_trigger_prediction_step_s": 0.1,
            "oracle_yield_passed_margin_m": 0.5,
            "oracle_yield_maximum_retreat_m": 1.4,
            "oracle_yield_recurrence_progress_m": 0.75,
            "oracle_yield_maximum_recurrences_without_progress": 1,
        }
        for name, value in numeric_defaults.items():
            self.declare_parameter(name, value)

    def _float(self, name: str) -> float:
        return float(self.get_parameter(name).value)

    def _integer(self, name: str) -> int:
        return int(self.get_parameter(name).value)

    def _subscribe(self) -> None:
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._subscription_handles.extend(
            [
                self.create_subscription(
                    Odometry,
                    str(self.get_parameter("odom_topic").value),
                    self._on_odom,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    LaserScan,
                    str(self.get_parameter("scan_topic").value),
                    self._on_scan,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    Twist,
                    str(self.get_parameter("base_cmd_vel_topic").value),
                    self._on_base_action,
                    10,
                ),
                self.create_subscription(
                    PathMessage,
                    str(self.get_parameter("global_path_topic").value),
                    self._on_path,
                    10,
                ),
                self.create_subscription(
                    OccupancyGridMessage,
                    str(self.get_parameter("map_topic").value),
                    self._on_map,
                    map_qos,
                ),
                self.create_subscription(
                    GoalStatusArray,
                    str(self.get_parameter("nav_status_topic").value),
                    self._on_status,
                    10,
                ),
                self.create_subscription(
                    FailureStatus,
                    str(self.get_parameter("failure_status_topic").value),
                    self._on_failure,
                    10,
                ),
                self.create_subscription(
                    PoseArray,
                    str(self.get_parameter("privileged_humans_topic").value),
                    self._on_humans,
                    qos_profile_sensor_data,
                ),
            ]
        )

    def _world_pose(self) -> Pose2D:
        assert self._odom is not None
        local = self._odom.pose.pose.position
        local_yaw = _yaw_from_odometry(self._odom)
        if bool(self.get_parameter("odometry_is_world_frame").value):
            return Pose2D(float(local.x), float(local.y), local_yaw)
        return Pose2D(
            self._start.x
            + math.cos(self._start.yaw) * local.x
            - math.sin(self._start.yaw) * local.y,
            self._start.y
            + math.sin(self._start.yaw) * local.x
            + math.cos(self._start.yaw) * local.y,
            math.atan2(
                math.sin(self._start.yaw + local_yaw),
                math.cos(self._start.yaw + local_yaw),
            ),
        )

    def _on_odom(self, message: Odometry) -> None:
        self._odom = message
        if self._ready_since_s is None:
            self._ready_since_s = self.get_clock().now().nanoseconds * 1.0e-9
        pose = self._world_pose()
        if self._initial_world_position is None:
            self._initial_world_position = pose.x, pose.y
        elif math.dist(self._initial_world_position, (pose.x, pose.y)) >= 0.05:
            self._movement_observed = True
            self._try_arm()
        self._distance_history.append(math.dist((pose.x, pose.y), (self._goal.x, self._goal.y)))
        self._angular_history.append(float(message.twist.twist.angular.z))

    def _on_scan(self, message: LaserScan) -> None:
        source = sanitize_near_field_returns(
            message.ranges,
            minimum_valid_range_m=self._float("minimum_valid_lidar_range_m"),
            bilateral_edge_self_return_max_m=self._float("bilateral_edge_self_return_max_m"),
        ).astype(np.float32)
        if source.size == 0:
            return
        maximum = float(message.range_max) if message.range_max > 0.0 else 30.0
        source = np.nan_to_num(source, nan=maximum, posinf=maximum, neginf=0.0)
        sample = np.interp(
            np.linspace(0.0, source.size - 1.0, 180), np.arange(source.size), source
        ).astype(np.float32)
        message.ranges = source.astype(float).tolist()
        self._scan = message
        self._lidar_stack.append(sample)

    def _on_base_action(self, message: Twist) -> None:
        self._base_action[:] = message.linear.x, message.angular.z
        self._adapter.update_last_command(message.linear.x, message.angular.z)

    def _on_path(self, message: PathMessage) -> None:
        frame = message.header.frame_id.rstrip("/")
        if frame.endswith("odom"):
            cosine = math.cos(self._start.yaw)
            sine = math.sin(self._start.yaw)
            path = tuple(
                (
                    self._start.x + cosine * pose.pose.position.x - sine * pose.pose.position.y,
                    self._start.y + sine * pose.pose.position.x + cosine * pose.pose.position.y,
                )
                for pose in message.poses
            )
        else:
            path = tuple((pose.pose.position.x, pose.pose.position.y) for pose in message.poses)
        # The policy observation and expert rejoin cost are defined against
        # the task-level path, not the temporary recovery-goal path. Nav2 uses
        # the same Path topic for both, so preserve the last task-level path
        # until the original goal has been restored.
        if not self._goal_preempted:
            self._path = path
            # Anchor the safety corridor to the first task-level plan.  Nav2
            # republishes locally deformed paths while recovering; replacing
            # this anchor would allow repeated relative subgoals to ratchet
            # the nominal corridor toward unmodeled Gazebo shelf geometry.
            if path and not self._task_corridor_path:
                self._task_corridor_path = path

    def _on_map(self, message: OccupancyGridMessage) -> None:
        width = int(message.info.width)
        height = int(message.info.height)
        if width <= 0 or height <= 0 or len(message.data) != width * height:
            return
        values = np.asarray(message.data, dtype=np.int16).reshape(height, width)
        self._map = OccupancyGrid(
            values != 0,
            float(message.info.resolution),
            float(message.info.origin.position.x),
            float(message.info.origin.position.y),
        )

    def _on_status(self, message: GoalStatusArray) -> None:
        if message.status_list:
            self._planner_status = select_planner_status(
                [_planner_status(int(item.status)) for item in message.status_list]
            )
            self._try_arm()

    def _on_failure(self, message: FailureStatus) -> None:
        self._failure = FailurePrediction(
            float(message.collision_risk),
            float(message.freeze),
            float(message.oscillation),
            float(message.deadlock),
        )
        # The control timer runs faster than the high-level decision timer.
        # Latch an actionable warning in this callback so a turning approach
        # cannot travel for another decision period with the generic margin.
        if self._failure.collision_risk >= self._float("bc_rejoin_block_threshold"):
            self._collision_safety_latched = True
        self._try_arm()

    def _on_humans(self, message: PoseArray) -> None:
        timestamp_s = float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1.0e-9
        positions = tuple(
            (float(pose.position.x), float(pose.position.y)) for pose in message.poses
        )
        elapsed_s = (
            0.0
            if self._previous_human_timestamp_s is None
            else max(0.0, timestamp_s - self._previous_human_timestamp_s)
        )
        self._privileged_humans = estimate_human_states(
            positions,
            self._previous_human_positions,
            elapsed_s,
            radius_m=self._float("human_radius_m"),
            maximum_speed_mps=self._float("maximum_human_speed_mps"),
        )
        self._previous_human_positions = positions
        self._previous_human_timestamp_s = timestamp_s
        self._received_privileged_humans = True

    def _try_arm(self) -> None:
        now_s = self.get_clock().now().nanoseconds * 1.0e-9
        nominal_ready = (
            self._movement_observed
            and self._planner_status is PlannerStatus.ACTIVE
            and self._failure.score < self._machine.config.tau_off
        )
        startup_failure_ready = (
            self._ready_since_s is not None
            and now_s - self._ready_since_s >= self._float("startup_failure_arm_s")
            and self._planner_status in {PlannerStatus.ABORTED, PlannerStatus.NO_VALID_CONTROL}
            and self._failure.score > self._machine.config.tau_on
        )
        if not self._armed and (nominal_ready or startup_failure_ready):
            self._armed = True
            self._armed_at_s = now_s
            self._distance_history.clear()
            self._angular_history.clear()

    def _effective_failure(self, pose: Pose2D) -> FailurePrediction:
        if (
            self._policy_type != "expert"
            or self._odom is None
            or not self._received_privileged_humans
        ):
            return self._failure
        planned_velocity = Velocity2D(
            float(self._base_action[0]),
            float(self._base_action[1]),
        )
        oracle_collision_time = privileged_time_to_collision(
            pose,
            planned_velocity,
            self._privileged_humans,
            horizon_s=self._float("oracle_trigger_horizon_s"),
            robot_radius_m=self._float("robot_radius_m"),
            prediction_margin_m=self._float("oracle_trigger_margin_m"),
            prediction_step_s=self._float("oracle_trigger_prediction_step_s"),
        )
        oracle_risk = oracle_collision_time is not None and oracle_collision_time <= self._float(
            "oracle_trigger_intervention_horizon_s"
        )
        yielding = self._oracle_yield.update(
            pose,
            self._privileged_humans,
            collision_risk=oracle_risk,
        )
        return FailurePrediction(
            max(self._failure.collision_risk, float(oracle_risk or yielding)),
            self._failure.freeze,
            self._failure.oscillation,
            self._failure.deadlock,
        )

    def _observation(self, failure: FailurePrediction | None = None) -> RecoveryObservation:
        pose = self._world_pose()
        distance = math.dist((pose.x, pose.y), (self._goal.x, self._goal.y))
        bearing = math.atan2(self._goal.y - pose.y, self._goal.x - pose.x) - pose.yaw
        bearing = math.atan2(math.sin(bearing), math.cos(bearing))
        points = navigation_path_or_goal(self._path, (self._goal.x, self._goal.y))
        waypoints = select_local_path_waypoints(points, pose)
        lidar = list(self._lidar_stack)
        lidar = [lidar[0]] * (5 - len(lidar)) + lidar
        progress = list(self._distance_history)
        progress = [distance] * (10 - len(progress)) + progress
        angular = list(self._angular_history)
        angular = [0.0] * (10 - len(angular)) + angular
        twist = self._odom.twist.twist
        return RecoveryObservation(
            lidar=np.asarray(lidar[-5:], dtype=np.float32),
            goal_polar=np.asarray([distance, bearing], dtype=np.float32),
            path_waypoints=waypoints,
            robot_velocity=np.asarray([twist.linear.x, twist.angular.z], dtype=np.float32),
            base_action=self._base_action.copy(),
            progress_history=np.asarray(progress[-10:], dtype=np.float32),
            angular_velocity_history=np.asarray(angular[-10:], dtype=np.float32),
            planner_status=self._planner_status,
            failure_prediction=self._failure if failure is None else failure,
        )

    def _laser_clearance(self, angle: float) -> float:
        assert self._scan is not None
        clearance = directional_scan_clearance(
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            direction=angle,
            half_width_rad=math.radians(12.0),
        )
        if clearance is not None:
            return clearance
        values = np.asarray(self._scan.ranges, dtype=np.float64)
        finite = values[np.isfinite(values) & (values >= 0.0)]
        return float(np.min(finite)) if finite.size else 0.0

    def _observed_laser_clearance(self, angle: float) -> float | None:
        assert self._scan is not None
        return directional_scan_clearance(
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            direction=angle,
            half_width_rad=math.radians(12.0),
        )

    def _motion_clearance(self, linear_velocity: float) -> float:
        """Measure clearance along the direction used by the braking model."""
        return self._laser_clearance(0.0 if linear_velocity >= 0.0 else math.pi)

    def _observable_nearest_clearance(self) -> float | None:
        """Return the nearest finite LiDAR clearance, preserving observability."""
        assert self._scan is not None
        values = np.asarray(self._scan.ranges, dtype=np.float64)
        finite = values[np.isfinite(values) & (values >= 0.0)]
        return float(np.min(finite)) if finite.size else None

    def _nearest_clearance(self) -> float:
        observed = self._observable_nearest_clearance()
        return 0.0 if observed is None else observed

    def _nearest_obstacle_angle(self) -> float:
        assert self._scan is not None
        values = np.asarray(self._scan.ranges, dtype=np.float64)
        valid = np.isfinite(values) & (values >= 0.0)
        if not bool(valid.any()):
            return math.pi
        valid_indices = np.flatnonzero(valid)
        closest_index = int(valid_indices[np.argmin(values[valid])])
        return float(self._scan.angle_min) + closest_index * float(self._scan.angle_increment)

    def _forward_escape_clearance(self) -> float:
        """Return forward clearance only when the footprint corridor is free."""
        assert self._scan is not None
        travel = (
            self._float("emergency_forward_speed_mps") * self._float("emergency_backup_duration_s")
            + 0.10
        )
        translation_clearance = self._float("emergency_translation_clearance_m")
        if self._collision_safety_latched:
            translation_clearance = collision_latched_motion_clearance(
                configured_action_clearance_m=translation_clearance,
                stop_clearance_m=self._float("collision_latched_stop_clearance_m"),
                release_hysteresis_m=self._float("emergency_release_hysteresis_m"),
            )
        corridor_path = self._task_corridor_path or self._path
        if corridor_path:
            pose = self._world_pose()
            target = (
                pose.x + travel * math.cos(pose.yaw),
                pose.y + travel * math.sin(pose.yaw),
            )
            if not path_corridor_target_is_permitted(
                (pose.x, pose.y),
                target,
                corridor_path,
                maximum_deviation_m=self._float("maximum_recovery_path_deviation_m"),
            ):
                return 0.0
        if not scan_segment_is_free(
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            target=(travel, 0.0),
            clearance_m=translation_clearance,
            allow_initial_overlap_when_separating=True,
        ):
            return 0.0
        return self._laser_clearance(0.0)

    def _footprint_stop_distance(self, linear_velocity: float) -> float:
        margin = self._float("footprint_stop_clearance_m")
        if self._collision_safety_latched:
            margin = max(margin, self._float("collision_latched_stop_clearance_m"))
        return stopping_distance(
            abs(linear_velocity),
            self._float("braking_acceleration_mps2"),
            self._float("control_latency_s"),
            margin,
        )

    def _footprint_backup_permitted(self, footprint_hazard: bool) -> bool:
        return not footprint_hazard or backup_increases_obstacle_clearance(
            self._nearest_obstacle_angle(),
            maximum_forward_angle_rad=math.radians(
                self._float("footprint_backup_forward_angle_degrees")
            ),
        )

    def _action_mask(
        self,
        pose: Pose2D,
        grid: OccupancyGrid | None = None,
        human_positions: tuple[tuple[float, float], ...] = (),
        collision_risk: float = 0.0,
    ) -> np.ndarray[Any, np.dtype[np.bool_]]:
        planning_grid = self._map if grid is None else grid
        if planning_grid is None:
            mask = np.ones(ACTION_COUNT, dtype=np.bool_)
        else:
            mask = compute_action_mask(
                pose,
                planning_grid,
                human_positions,
                replan_available=self._adapter.ready,
                config=ActionMaskConfig(
                    robot_clearance=self._float("robot_clearance_m"),
                    backup_distance=self._float("backup_mask_validated_distance_m"),
                ),
            )
        action_clearance = self._float("robot_clearance_m")
        swept_clearance = self._float("footprint_stop_clearance_m")
        if collision_risk >= self._float("bc_rejoin_block_threshold"):
            action_clearance = collision_latched_motion_clearance(
                configured_action_clearance_m=max(
                    action_clearance,
                    self._float("collision_latched_action_clearance_m"),
                ),
                stop_clearance_m=self._float("collision_latched_stop_clearance_m"),
                release_hysteresis_m=self._float("emergency_release_hysteresis_m"),
            )
            swept_clearance = max(swept_clearance, action_clearance)
        mask = apply_observable_scan_mask(
            mask,
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            swept_clearance_m=swept_clearance,
            target_clearance_m=action_clearance,
            backup_distance_m=self._float("backup_mask_validated_distance_m"),
            allow_unobserved_backup=(
                self._policy_type == "expert" and self._received_privileged_humans
            ),
        )
        corridor_path = self._task_corridor_path or self._path
        if corridor_path:
            mask = apply_path_corridor_mask(
                mask,
                pose,
                corridor_path,
                maximum_deviation_m=self._float("maximum_recovery_path_deviation_m"),
                backup_distance_m=self._float("backup_mask_validated_distance_m"),
            )
        mask[REPLAN_ACTION_ID] &= self._adapter.ready
        mask[WAIT_ACTION_ID] = True
        mask[CONTINUE_ACTION_ID] = True
        return mask

    def _expert_decision(
        self,
        pose: Pose2D,
        failure: FailurePrediction,
    ) -> CoreRecoveryDecision:
        if self._map is None or self._scan is None or not self._received_privileged_humans:
            return CoreRecoveryDecision(
                WAIT_ACTION_ID,
                0.0,
                "oracle_unavailable_wait",
            )
        grid = augment_grid_with_scan(
            self._map,
            pose,
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            minimum_range_m=max(0.05, float(self._scan.range_min)),
            maximum_range_m=float(self._scan.range_max),
            inflation_m=self._float("expert_scan_inflation_m"),
        )
        human_positions = tuple(human.position for human in self._privileged_humans)
        mask = self._action_mask(
            pose,
            grid,
            human_positions,
            collision_risk=failure.collision_risk,
        )
        mask = constrain_rejoin_actions(
            mask,
            collision_risk=failure.collision_risk,
            release_threshold=self._float("expert_rejoin_block_threshold"),
        )
        expert_wait_budget = self._integer("expert_wait_budget_decisions")
        mask = constrain_stalled_wait(
            mask,
            consecutive_waits=self._expert_repeated_waits,
            wait_budget=expert_wait_budget,
        )
        mask = constrain_recurrent_yield_escape(
            mask,
            escape_required=self._oracle_yield.escape_required,
        )
        if self._oracle_yield.active and not self._oracle_yield.escape_required:
            action_id = (
                BACKUP_ACTION_ID
                if self._oracle_yield.backup_required and mask[BACKUP_ACTION_ID]
                else WAIT_ACTION_ID
            )
            return CoreRecoveryDecision(
                action_id,
                1.0,
                ("oracle_yield_backup" if action_id == BACKUP_ACTION_ID else "oracle_yield_wait"),
            )
        twist = self._odom.twist.twist
        privileged = PrivilegedState(
            robot_pose=pose,
            robot_velocity=Velocity2D(float(twist.linear.x), float(twist.angular.z)),
            original_goal=self._goal,
            global_path=self._path if self._path else ((self._goal.x, self._goal.y),),
            humans=self._privileged_humans,
            time_step=0.1,
        )
        label = PlanningRecoveryExpert(grid).label(
            privileged,
            mask,
            previous_side=self._expert_previous_side,
            repeated_waits=self._expert_repeated_waits,
        )
        self._expert_previous_side, self._expert_repeated_waits = update_expert_history(
            label.action_id,
            previous_side=self._expert_previous_side,
            repeated_waits=self._expert_repeated_waits,
        )
        confidence = min(1.0, label.margin / (1.0 + abs(label.best_cost)))
        return CoreRecoveryDecision(
            label.action_id,
            confidence,
            (
                (
                    "oracle_recurrent_yield_escape "
                    if self._oracle_yield.escape_required
                    else "oracle_rollout "
                )
                + f"best={label.best_cost:.3f} margin={label.margin:.3f} "
                f"predicted_success={int(label.predicted_success)}"
            ),
        )

    def _select_decision(
        self,
        observation: RecoveryObservation,
        pose: Pose2D,
        failure: FailurePrediction,
        *,
        stalled_rejoin: bool = False,
    ) -> CoreRecoveryDecision:
        if self._policy_type == "expert":
            try:
                return self._expert_decision(pose, failure)
            except (RuntimeError, ValueError) as error:
                self.get_logger().error(f"privileged expert failed safely: {error}")
                return CoreRecoveryDecision(WAIT_ACTION_ID, 0.0, "oracle_error_wait")
        mask = self._action_mask(pose, collision_risk=failure.collision_risk)
        if self._policy_type == "bc":
            self._update_bc_progress_budget(float(observation.goal_polar[0]))
            mask = constrain_rejoin_actions(
                mask,
                collision_risk=failure.collision_risk,
                release_threshold=self._float("bc_rejoin_block_threshold"),
            )
            mask = constrain_stalled_rejoin(mask, escape_required=stalled_rejoin)
            bc_wait_budget = self._integer("bc_wait_budget_decisions")
            mask = constrain_stalled_wait(
                mask,
                consecutive_waits=self._bc_waits_without_progress,
                wait_budget=bc_wait_budget,
            )
            mask = constrain_repeated_replan(
                mask,
                replan_count=self._bc_replans_without_progress,
                replan_budget=self._integer("bc_replan_budget_decisions"),
            )
            mask = constrain_repeated_backup(
                mask,
                backup_count=self._bc_backups_without_progress,
                backup_budget=self._integer("bc_backup_budget_decisions"),
            )
        decision = self._policy.select_action(observation, mask)
        if self._policy_type == "bc":
            if decision.action_id == WAIT_ACTION_ID:
                self._bc_waits_without_progress += 1
            elif decision.action_id == BACKUP_ACTION_ID:
                self._bc_backups_without_progress += 1
            elif decision.action_id == REPLAN_ACTION_ID:
                self._bc_replans_without_progress += 1
        return decision

    def _update_bc_progress_budget(self, distance_to_goal_m: float) -> None:
        """Reset anti-stall budgets only after meaningful cumulative progress."""
        if not math.isfinite(distance_to_goal_m) or distance_to_goal_m < 0.0:
            raise ValueError("distance to goal must be finite and non-negative")
        if self._bc_progress_reference_distance_m is None:
            self._bc_progress_reference_distance_m = distance_to_goal_m
            return
        if self._bc_progress_reference_distance_m - distance_to_goal_m < self._float(
            "bc_progress_reset_m"
        ):
            return
        self._bc_progress_reference_distance_m = distance_to_goal_m
        self._bc_waits_without_progress = 0
        self._bc_backups_without_progress = 0
        self._bc_replans_without_progress = 0

    def _valid_progress(self) -> bool:
        if len(self._distance_history) < 2:
            return False
        return self._distance_history[0] - self._distance_history[-1] > 0.03

    def _action_complete(self, now_s: float) -> bool:
        elapsed = now_s - self._action_started_s
        if self._active_action == WAIT_ACTION_ID:
            return elapsed >= self._float("wait_duration_s")
        if self._active_action == BACKUP_ACTION_ID:
            return self._backup_option.is_complete(
                elapsed_s=elapsed,
                start_clearance_m=self._backup_start_clearance_m,
                current_clearance_m=self._observable_nearest_clearance(),
            )
        if self._active_action in {REPLAN_ACTION_ID, CONTINUE_ACTION_ID}:
            return elapsed >= self._float("minimum_action_hold_s")
        if self._policy_type == "expert":
            return elapsed >= self._float("expert_replan_interval_s")
        if self._policy_type == "bc":
            return elapsed >= self._float("bc_action_interval_s")
        return self._adapter.get_status() is PlannerStatus.SUCCEEDED

    def _execute(self, action_id: int, now_s: float) -> Pose2D | None:
        self._active_action = action_id
        self._action_started_s = now_s
        self._backup_start_clearance_m = (
            self._observable_nearest_clearance() if action_id == BACKUP_ACTION_ID else None
        )
        action = ACTIONS[action_id]
        if action.kind is RecoveryActionKind.SUBGOAL:
            temporary = action.target_pose(self._world_pose())
            assert temporary is not None
            self._adapter.set_recovery_goal(temporary)
            self._goal_preempted = True
            return temporary
        if action_id in {REPLAN_ACTION_ID, CONTINUE_ACTION_ID}:
            self._adapter.restore_original_goal()
            self._goal_preempted = False
        return None

    def _publish_decision(
        self,
        action_id: int,
        confidence: float,
        reason: str,
        temporary: Pose2D | None = None,
    ) -> None:
        message = RecoveryDecision()
        message.stamp = self.get_clock().now().to_msg()
        message.action_id = action_id
        message.action_name = ACTIONS[action_id].kind.value
        message.confidence = confidence
        message.has_temporary_goal = temporary is not None
        message.recovery_state = STATE_IDS[self._machine.state]
        message.reason = reason
        if temporary is not None:
            message.temporary_goal = PoseStamped()
            message.temporary_goal.header.stamp = message.stamp
            message.temporary_goal.header.frame_id = str(self.get_parameter("map_frame").value)
            message.temporary_goal.pose.position.x = temporary.x
            message.temporary_goal.pose.position.y = temporary.y
            message.temporary_goal.pose.orientation.z = math.sin(temporary.yaw / 2.0)
            message.temporary_goal.pose.orientation.w = math.cos(temporary.yaw / 2.0)
        self._decision_publisher.publish(message)

    def _decision_step(self) -> None:
        if not self._armed or self._odom is None or self._scan is None or not self._lidar_stack:
            return
        now_s = self.get_clock().now().nanoseconds * 1.0e-9
        if now_s - self._armed_at_s < self._float("arming_grace_s"):
            return
        pose = self._world_pose()
        failure = self._effective_failure(pose)
        distance = math.dist((pose.x, pose.y), (self._goal.x, self._goal.y))
        velocity = max(0.0, float(self._odom.twist.twist.linear.x))
        stop = stopping_distance(
            velocity,
            self._float("braking_acceleration_mps2"),
            self._float("control_latency_s"),
            self._float("stopping_margin_m"),
        )
        motion_clearance = self._motion_clearance(float(self._odom.twist.twist.linear.x))
        nearest_clearance = self._nearest_clearance()
        self._collision_safety_latched = update_collision_safety_latch(
            latched=self._collision_safety_latched,
            collision_risk=failure.collision_risk,
            trigger_threshold=self._float("bc_rejoin_block_threshold"),
            footprint_clearance_m=nearest_clearance,
            release_clearance_m=(
                self._float("collision_latched_stop_clearance_m")
                + self._float("emergency_release_hysteresis_m")
            ),
        )
        footprint_stop = self._footprint_stop_distance(float(self._odom.twist.twist.linear.x))
        footprint_hazard = nearest_clearance < footprint_stop
        raw_emergency = emergency_hazard_with_hysteresis(
            emergency_active=self._emergency,
            motion_clearance_m=motion_clearance,
            motion_stop_distance_m=stop,
            footprint_clearance_m=nearest_clearance,
            footprint_stop_distance_m=footprint_stop,
            release_hysteresis_m=self._float("emergency_release_hysteresis_m"),
        )
        rear_clearance = self._observed_laser_clearance(math.pi)
        nearest_angle = self._nearest_obstacle_angle()
        self._emergency, self._emergency_escape_mode = self._emergency_escape.update(
            now_s=now_s,
            hazard=raw_emergency,
            linear_speed_mps=float(self._odom.twist.twist.linear.x),
            rear_clearance_m=0.0 if rear_clearance is None else rear_clearance,
            backup_permitted=self._footprint_backup_permitted(footprint_hazard),
            obstacle_angle_rad=nearest_angle,
            obstacle_clearance_m=nearest_clearance,
            forward_clearance_m=self._forward_escape_clearance(),
            rear_observed=rear_clearance is not None,
        )
        self._emergency_escape_active = self._emergency_escape_mode is EmergencyEscapeMode.BACKUP
        action_complete = self._machine.state is RecoveryState.RECOVERY and self._action_complete(
            now_s
        )
        persistent_failure_followup = should_continue_recovery_option(
            policy_type=self._policy_type,
            action_id=self._active_action,
            action_complete=action_complete,
            failure_score=failure.score,
            tau_off=self._machine.config.tau_off,
            option_elapsed_s=now_s - self._machine.state_since_s,
            maximum_option_duration_s=self._machine.config.maximum_recovery_duration_s,
        )
        transition = self._machine.update(
            StateMachineInput(
                now_s=now_s,
                failure_score=failure.score,
                valid_progress=self._valid_progress(),
                emergency_stop=self._emergency,
                goal_reached=distance <= self._float("goal_tolerance_m"),
                recovery_action_complete=action_complete and not persistent_failure_followup,
                recovery_option_active=self._oracle_yield.active,
            )
        )
        if transition.current is not RecoveryState.RECOVERY:
            self._backup_start_clearance_m = None
        if transition.current is RecoveryState.RECOVERY and (
            transition.changed or persistent_failure_followup
        ):
            observation = self._observation(failure)
            decision_failure = failure
            if self._collision_safety_latched and failure.collision_risk < self._float(
                "bc_rejoin_block_threshold"
            ):
                decision_failure = FailurePrediction(
                    collision_risk=self._float("bc_rejoin_block_threshold"),
                    freeze=failure.freeze,
                    oscillation=failure.oscillation,
                    deadlock=failure.deadlock,
                )
            decision = self._select_decision(
                observation,
                pose,
                decision_failure,
                stalled_rejoin=transition.reason == "rejoin_failure_retry",
            )
            temporary = self._execute(decision.action_id, now_s)
            self._publish_decision(
                decision.action_id, decision.confidence, decision.reason, temporary
            )
        elif transition.current is RecoveryState.REJOIN and transition.changed:
            # Re-submit even after WAIT/BACKUP. Nav2 may have aborted or stopped
            # its controller while the direct velocity override was active, in
            # which case merely removing the override leaves REJOIN waiting for
            # progress that can never resume.
            if self._adapter.restore_original_goal():
                self._goal_preempted = False
            self._publish_decision(CONTINUE_ACTION_ID, failure.score, transition.reason)
        elif transition.current is RecoveryState.EMERGENCY_STOP and transition.changed:
            self._active_action = (
                BACKUP_ACTION_ID if self._emergency_escape_active else WAIT_ACTION_ID
            )
            self._action_started_s = now_s
            self._published_emergency_mode = self._emergency_escape_mode
            self._publish_decision(
                self._active_action,
                1.0,
                emergency_mode_reason(self._emergency_escape_mode),
            )
        elif (
            transition.current is RecoveryState.EMERGENCY_STOP
            and self._emergency_escape_mode is not self._published_emergency_mode
        ):
            self._active_action = (
                BACKUP_ACTION_ID if self._emergency_escape_active else WAIT_ACTION_ID
            )
            self._action_started_s = now_s
            self._published_emergency_mode = self._emergency_escape_mode
            self._publish_decision(
                self._active_action,
                1.0,
                emergency_mode_reason(self._emergency_escape_mode),
            )
        elif transition.previous is RecoveryState.EMERGENCY_STOP and transition.changed:
            self._published_emergency_mode = None
            self._publish_decision(
                CONTINUE_ACTION_ID, failure.score, "emergency_clear_continue_goal"
            )
        elif (
            transition.current is RecoveryState.NORMAL
            and transition.previous is RecoveryState.REJOIN
        ):
            self._policy.reset()
            if transition.reason == "original_goal_restored":
                self._expert_previous_side = 0
                self._expert_repeated_waits = 0
            self._publish_decision(CONTINUE_ACTION_ID, failure.score, transition.reason)
        elif transition.changed:
            self._publish_decision(CONTINUE_ACTION_ID, failure.score, transition.reason)

    def _control_step(self) -> None:
        command: Twist | None = None
        immediate_safety_stop = False
        now_s = self.get_clock().now().nanoseconds * 1.0e-9
        if self._odom is not None and self._lidar_stack:
            velocity = max(0.0, float(self._odom.twist.twist.linear.x))
            stop = stopping_distance(
                velocity,
                self._float("braking_acceleration_mps2"),
                self._float("control_latency_s"),
                self._float("stopping_margin_m"),
            )
            linear_velocity = float(self._odom.twist.twist.linear.x)
            immediate_safety_stop = self._motion_clearance(
                linear_velocity
            ) < stop or self._nearest_clearance() < self._footprint_stop_distance(linear_velocity)
        footprint_hazard = self._scan is not None and self._nearest_clearance() < self._float(
            "footprint_stop_clearance_m"
        )
        if (
            self._machine.state is RecoveryState.EMERGENCY_STOP
            and self._emergency_escape_mode is EmergencyEscapeMode.BACKUP
            and self._footprint_backup_permitted(footprint_hazard)
        ):
            rear_stop = stopping_distance(
                self._float("backup_speed_mps"),
                self._float("braking_acceleration_mps2"),
                self._float("control_latency_s"),
                self._float("stopping_margin_m"),
            )
            command = Twist()
            if self._laser_clearance(math.pi) >= rear_stop:
                command.linear.x = -self._float("backup_speed_mps")
        elif (
            self._machine.state is RecoveryState.EMERGENCY_STOP
            and self._emergency_escape_mode is EmergencyEscapeMode.FORWARD
        ):
            command = Twist()
            if self._forward_escape_clearance() >= self._float(
                "emergency_forward_entry_clearance_m"
            ):
                command.linear.x = self._float("emergency_forward_speed_mps")
        elif (
            self._machine.state is RecoveryState.EMERGENCY_STOP
            and self._emergency_escape_mode
            in {EmergencyEscapeMode.TURN_LEFT, EmergencyEscapeMode.TURN_RIGHT}
        ):
            command = Twist()
            direction = (
                1.0 if self._emergency_escape_mode is EmergencyEscapeMode.TURN_LEFT else -1.0
            )
            command.angular.z = direction * self._float("emergency_turn_speed_radps")
        elif (
            immediate_safety_stop
            or self._machine.state is RecoveryState.EMERGENCY_STOP
            or (
                self._machine.state is RecoveryState.RECOVERY
                and self._active_action == WAIT_ACTION_ID
            )
        ):
            command = Twist()
        elif (
            self._machine.state is RecoveryState.RECOVERY
            and ACTIONS[self._active_action].kind is RecoveryActionKind.SUBGOAL
            and now_s - self._action_started_s < self._float("subgoal_settle_s")
        ):
            # Goal submission and replanning are asynchronous. Prevent a stale
            # original-goal command from leaking through during preemption.
            command = Twist()
        elif (
            self._machine.state is RecoveryState.RECOVERY
            and self._active_action == BACKUP_ACTION_ID
        ):
            command = Twist()
            # Stop issuing the direct command at the same duration used by the
            # completion rule.  Even if the slower decision timer is delayed,
            # ideal commanded travel therefore cannot exceed the 0.45 m rear
            # segment checked by the planning and observable-scan masks.
            if now_s - self._action_started_s < self._backup_option.maximum_duration_s:
                command.linear.x = -self._float("backup_speed_mps")
        if command is not None:
            self._override_publisher.publish(command)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: RecoveryManagerNode | None = None
    try:
        node = RecoveryManagerNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
