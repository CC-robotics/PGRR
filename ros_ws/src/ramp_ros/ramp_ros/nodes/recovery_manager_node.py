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
from ramp_core.geometry import nearest_polyline_tangent_heading
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
    fully_observed_directional_scan_clearance,
    privileged_time_to_collision,
    sanitize_near_field_returns,
    scan_segment_is_free,
)
from ramp_core.recovery.heuristic import HeuristicRecoveryConfig, HeuristicRecoveryPolicy
from ramp_core.recovery.options import (
    BoundedBackupOption,
    BoundedSubgoalOption,
    ObservableClosingSideLatch,
    ObservableDirectionalYieldLatch,
    ObservableGoalProgressBudget,
    ObservableLateralSideCommitment,
    ObservableNetRetreatGuard,
    ObservableSubgoalStallGuard,
    PrivilegedYieldOption,
    TemporalClosingSideConfig,
    TemporalClosingSideResult,
    constrain_committed_lateral_side,
    constrain_directional_yield_motion,
    constrain_near_field_subgoal_radius,
    constrain_net_retreat,
    constrain_recurrent_yield_escape,
    constrain_rejoin_actions,
    constrain_repeated_backup,
    constrain_repeated_replan,
    constrain_stalled_rejoin,
    constrain_stalled_subgoals,
    constrain_stalled_wait,
    constrain_task_lateral_sides,
    constrain_temporal_closing_side,
    effective_recovery_path_deviation,
    ensure_safe_wait_fallback,
    orient_subgoal_for_rejoin,
    recurrent_yield_lateral_action_ids,
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
    StateTransition,
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
        if self._integer("bc_recurrent_escape_after_recoveries") <= 0:
            raise ValueError("BC recurrent escape threshold must be positive")
        recurrent_lateral_displacement = self._float(
            "recurrent_escape_minimum_lateral_displacement_m"
        )
        if not math.isfinite(recurrent_lateral_displacement) or recurrent_lateral_displacement <= 0:
            raise ValueError("recurrent escape minimum lateral displacement must be positive")
        effective_recovery_path_deviation(
            policy_type=self._policy_type,
            directional_yield_latched=False,
            consecutive_recoveries=0,
            recurrent_escape_after_recoveries=self._integer("bc_recurrent_escape_after_recoveries"),
            normal_maximum_deviation_m=self._float("maximum_recovery_path_deviation_m"),
            recurrent_maximum_deviation_m=self._float("recurrent_escape_maximum_path_deviation_m"),
        )
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
            maximum_recovery_sequence_duration_s=self._float(
                "maximum_recovery_sequence_duration_s"
            ),
            maximum_rejoin_duration_s=self._float("maximum_rejoin_duration_s"),
            maximum_rejoin_retries_per_sequence=self._integer(
                "maximum_rejoin_retries_per_sequence"
            ),
            maximum_consecutive_recoveries=self._integer("maximum_consecutive_recoveries"),
        )
        self._machine = RecoveryStateMachine(state_config)
        self._machine.set_original_goal(self._goal)
        self._bc_subgoal_option = BoundedSubgoalOption(
            settle_duration_s=self._float("subgoal_settle_s"),
            minimum_execution_duration_s=self._float("bc_subgoal_minimum_execution_s"),
            maximum_duration_s=self._float("bc_subgoal_maximum_duration_s"),
            recovery_limit_s=self._float("maximum_recovery_duration_s"),
            legacy_action_interval_s=self._float("bc_action_interval_s"),
        )
        self._backup_option = BoundedBackupOption(
            minimum_duration_s=self._float("backup_minimum_duration_s"),
            maximum_duration_s=self._float("backup_maximum_duration_s"),
            speed_mps=self._float("backup_speed_mps"),
            clearance_improvement_m=self._float("backup_clearance_improvement_m"),
            mask_validated_distance_m=self._float("backup_mask_validated_distance_m"),
        )
        self._bc_retreat_guard = ObservableNetRetreatGuard(
            task_heading_rad=math.atan2(
                self._goal.y - self._start.y,
                self._goal.x - self._start.x,
            ),
            maximum_net_retreat_m=self._float("bc_maximum_net_retreat_m"),
        )
        self._bc_yield_latch = ObservableDirectionalYieldLatch(
            trigger_threshold=self._machine.config.tau_on,
            release_clearance_m=self._float("bc_yield_release_clearance_m"),
            release_frames=self._integer("bc_yield_release_frames"),
        )
        self._bc_closing_side_config = TemporalClosingSideConfig(
            sector_min_degrees=self._float("bc_closing_side_sector_min_degrees"),
            sector_max_degrees=self._float("bc_closing_side_sector_max_degrees"),
            closing_delta_m=self._float("bc_closing_side_delta_m"),
            maximum_current_range_m=self._float("bc_closing_side_maximum_range_m"),
            minimum_closing_beams=self._integer("bc_closing_side_minimum_beams"),
            maximum_angular_speed_radps=self._float("bc_closing_side_maximum_angular_speed_radps"),
        )
        self._bc_closing_side_latch = ObservableClosingSideLatch()
        self._bc_lateral_side_commitment = ObservableLateralSideCommitment(
            maximum_progress_m=self._float("bc_lateral_commitment_progress_m"),
            maximum_heading_change_rad=math.radians(
                self._float("bc_lateral_commitment_maximum_heading_change_degrees")
            ),
        )
        self._bc_subgoal_stall_guard = ObservableSubgoalStallGuard(
            retry_budget=self._integer("bc_subgoal_retry_budget_decisions"),
            minimum_displacement_m=self._float("bc_subgoal_stall_displacement_m"),
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
        self._sequence_progress_budget = ObservableGoalProgressBudget(
            reset_progress_m=self._float("bc_progress_reset_m")
        )
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
            rotation_clearance_m=self._effective_emergency_rotation_clearance(),
            turn_duration_s=self._float("emergency_turn_duration_s"),
            maximum_turn_pulses=self._integer("emergency_maximum_turn_pulses"),
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
            "bc_subgoal_minimum_execution_s": 2.0,
            "bc_subgoal_maximum_duration_s": 6.0,
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
            "maximum_recovery_sequence_duration_s": 45.0,
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
            "maximum_recovery_path_deviation_m": 0.6,
            "recurrent_escape_maximum_path_deviation_m": 1.5,
            "backup_speed_mps": 0.15,
            "backup_minimum_duration_s": 0.8,
            "backup_maximum_duration_s": 3.0,
            "backup_clearance_improvement_m": 0.25,
            "backup_mask_validated_distance_m": 0.45,
            "wait_duration_s": 0.5,
            "subgoal_settle_s": 1.0,
            "expert_replan_interval_s": 0.5,
            "expert_wait_budget_decisions": 3,
            "bc_rejoin_block_threshold": 0.65,
            "bc_yield_release_clearance_m": 0.90,
            "bc_yield_release_frames": 3,
            "bc_near_field_radius_activation_clearance_m": 1.0,
            "bc_near_field_max_subgoal_radius_m": 0.6,
            "bc_yield_forward_half_width_degrees": 45.0,
            "bc_yield_maximum_forward_progress_m": 0.10,
            "bc_closing_side_sector_min_degrees": 5.0,
            "bc_closing_side_sector_max_degrees": 60.0,
            "bc_closing_side_delta_m": 0.20,
            "bc_closing_side_maximum_range_m": 4.0,
            "bc_closing_side_minimum_beams": 3,
            "bc_closing_side_maximum_angular_speed_radps": 0.20,
            "bc_lateral_commitment_progress_m": 3.0,
            "bc_lateral_commitment_maximum_heading_change_degrees": 45.0,
            "bc_wait_budget_decisions": 3,
            "bc_backup_budget_decisions": 4,
            "bc_replan_budget_decisions": 1,
            "bc_recurrent_escape_after_recoveries": 1,
            "recurrent_escape_minimum_lateral_displacement_m": 0.25,
            "bc_progress_reset_m": 0.25,
            "bc_maximum_net_retreat_m": 1.4,
            "bc_subgoal_retry_budget_decisions": 4,
            "bc_subgoal_stall_displacement_m": 0.08,
            "braking_acceleration_mps2": 0.8,
            "control_latency_s": 0.15,
            "stopping_margin_m": 0.45,
            "footprint_stop_clearance_m": 0.48,
            "collision_latched_stop_clearance_m": 0.85,
            "collision_latched_action_clearance_m": 0.90,
            "footprint_backup_forward_angle_degrees": 80.0,
            "emergency_hold_s": 0.5,
            "emergency_backup_duration_s": 0.8,
            "emergency_backup_clearance_m": 0.70,
            "emergency_release_speed_mps": 0.03,
            "emergency_release_hysteresis_m": 0.05,
            "footprint_release_hysteresis_m": 0.0,
            # This nominal geometric floor is composed with the stricter
            # footprint stop-and-release boundary before any turn is allowed.
            "emergency_rotation_clearance_m": 0.24,
            "emergency_turn_duration_s": 0.8,
            "emergency_maximum_turn_pulses": 4,
            "emergency_forward_entry_clearance_m": 0.85,
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
            self._bc_closing_side_latch.reset()
            self._bc_lateral_side_commitment.reset()
            self._oracle_yield.reset()
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

    def _task_path_heading(self, pose: Pose2D) -> float:
        """Return the local task-path tangent without using simulator truth."""

        corridor_path = self._task_corridor_path or self._path
        heading = nearest_polyline_tangent_heading((pose.x, pose.y), corridor_path)
        if heading is not None:
            return heading
        dx = self._goal.x - self._start.x
        dy = self._goal.y - self._start.y
        return math.atan2(dy, dx) if math.hypot(dx, dy) > 1.0e-9 else pose.yaw

    def _task_forward_clearance(self, pose: Pose2D) -> float | None:
        """Measure a fully observed LiDAR sector along the local task path."""

        task_heading = self._task_path_heading(pose)
        relative_heading = math.atan2(
            math.sin(task_heading - pose.yaw),
            math.cos(task_heading - pose.yaw),
        )
        return fully_observed_directional_scan_clearance(
            self._scan.ranges,
            angle_min=float(self._scan.angle_min),
            angle_increment=float(self._scan.angle_increment),
            direction=relative_heading,
            half_width_rad=math.radians(self._float("bc_yield_forward_half_width_degrees")),
            range_max=float(self._scan.range_max),
        )

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
                maximum_deviation_m=self._effective_recovery_path_deviation(),
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
        """Return the omnidirectional physical-footprint stop distance.

        A collision-risk latch describes an obstacle in the commanded motion
        sector.  Applying its larger dynamic margin to the nearest return in
        every direction lets a static side wall sustain an emergency forever
        after the approaching actor has gone.  The independent footprint
        margin remains active in every direction; the latched margin is
        applied by :meth:`_motion_stop_distance` in the actual direction of
        travel.
        """
        return stopping_distance(
            abs(linear_velocity),
            self._float("braking_acceleration_mps2"),
            self._float("control_latency_s"),
            self._float("footprint_stop_clearance_m"),
        )

    def _effective_emergency_rotation_clearance(self) -> float:
        """Return the observable swept margin required for emergency rotation."""

        return max(
            self._float("emergency_rotation_clearance_m"),
            self._float("footprint_stop_clearance_m")
            + self._float("emergency_release_hysteresis_m"),
        )

    def _motion_stop_distance(self, linear_velocity: float) -> float:
        """Return the directional stop distance, including a collision latch."""
        margin = self._float("stopping_margin_m")
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

    def _effective_recovery_path_deviation(self) -> float:
        """Return the active path regularizer without weakening safety masks."""

        return effective_recovery_path_deviation(
            policy_type=self._policy_type,
            directional_yield_latched=self._bc_yield_latch.latched,
            consecutive_recoveries=self._machine.consecutive_recoveries,
            recurrent_escape_after_recoveries=self._integer("bc_recurrent_escape_after_recoveries"),
            normal_maximum_deviation_m=self._float("maximum_recovery_path_deviation_m"),
            recurrent_maximum_deviation_m=self._float("recurrent_escape_maximum_path_deviation_m"),
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
            # A true dynamic-risk trigger can begin inside the deliberately
            # conservative 0.90 m planning margin.  Preserve that margin while
            # allowing only motions whose distance from every close return is
            # non-decreasing; otherwise every lateral yield is masked and the
            # only remaining learned option is repeated BACKUP.
            allow_initial_overlap_when_separating=(
                collision_risk >= self._float("bc_rejoin_block_threshold")
            ),
        )
        corridor_path = self._task_corridor_path or self._path
        if corridor_path:
            mask = apply_path_corridor_mask(
                mask,
                pose,
                corridor_path,
                maximum_deviation_m=self._effective_recovery_path_deviation(),
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
            release_threshold=self._machine.config.tau_on,
        )
        expert_wait_budget = self._integer("expert_wait_budget_decisions")
        mask = constrain_stalled_wait(
            mask,
            consecutive_waits=self._expert_repeated_waits,
            wait_budget=expert_wait_budget,
        )
        backup_mask_legal = bool(mask[BACKUP_ACTION_ID])
        self._oracle_yield.require_escape_if_retreat_unavailable(
            retreat_is_safe=backup_mask_legal,
        )
        if self._oracle_yield.active and not self._oracle_yield.backup_required:
            # The longitudinal distance budget is independent of the planning
            # mask.  Intersect it here before the recurrent escape constraint;
            # never re-authorize BACKUP after the bounded retreat is exhausted.
            mask[BACKUP_ACTION_ID] = False
        mask = constrain_recurrent_yield_escape(
            mask,
            escape_required=self._oracle_yield.escape_required,
            pose=pose,
            path_heading_rad=self._task_path_heading(pose),
            minimum_lateral_displacement_m=self._float(
                "recurrent_escape_minimum_lateral_displacement_m"
            ),
        )
        mask = ensure_safe_wait_fallback(mask)
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
                    "oracle_yield_escape "
                    f"cause={self._oracle_yield.escape_reason or 'unspecified'} "
                    f"backup_required={int(self._oracle_yield.backup_required)} "
                    f"backup_mask_legal={int(backup_mask_legal)}; "
                    if self._oracle_yield.escape_required
                    else "oracle_rollout "
                )
                + f"best={label.best_cost:.3f} margin={label.margin:.3f} "
                f"predicted_success={int(label.predicted_success)}"
            ),
        )

    def _constrain_bc_recurrent_escape(
        self,
        mask: np.ndarray[Any, np.dtype[np.bool_]],
        *,
        pose: Pose2D,
        path_heading_rad: float,
    ) -> np.ndarray[Any, np.dtype[np.bool_]]:
        """Require an already-legal lateral escape during a latched BC yield."""

        return constrain_recurrent_yield_escape(
            mask,
            escape_required=(
                self._bc_yield_latch.latched
                and self._machine.consecutive_recoveries
                >= self._integer("bc_recurrent_escape_after_recoveries")
            ),
            pose=pose,
            path_heading_rad=path_heading_rad,
            minimum_lateral_displacement_m=self._float(
                "recurrent_escape_minimum_lateral_displacement_m"
            ),
        )

    def _constrain_bc_temporal_closing_side(
        self,
        mask: np.ndarray[Any, np.dtype[np.bool_]],
        observation: RecoveryObservation,
        *,
        pose: Pose2D,
        path_heading_rad: float,
    ) -> TemporalClosingSideResult:
        """Intersect learned lateral choices with observable flow evidence."""

        assert self._scan is not None
        raw_result = constrain_temporal_closing_side(
            mask,
            observation.lidar,
            angle_min_rad=float(self._scan.angle_min),
            # The policy stack is resampled across the first and last raw
            # beams. Derive that exact endpoint from the scan metadata rather
            # than trusting publishers that leave angle_max at its default.
            angle_max_rad=float(self._scan.angle_min)
            + float(self._scan.angle_increment) * (len(self._scan.ranges) - 1),
            pose=pose,
            path_heading_rad=path_heading_rad,
            angular_speed_radps=float(observation.robot_velocity[1]),
            minimum_lateral_displacement_m=self._float(
                "recurrent_escape_minimum_lateral_displacement_m"
            ),
            config=self._bc_closing_side_config,
        )
        right_occupied, left_occupied = self._bc_closing_side_latch.update(
            yield_active=self._bc_yield_latch.latched,
            right_occupied=raw_result.right_occupied,
            left_occupied=raw_result.left_occupied,
            rotation_gated=raw_result.rotation_gated,
        )
        effective_mask = constrain_task_lateral_sides(
            raw_result.mask,
            pose=pose,
            path_heading_rad=path_heading_rad,
            minimum_lateral_displacement_m=self._float(
                "recurrent_escape_minimum_lateral_displacement_m"
            ),
            right_occupied=right_occupied,
            left_occupied=left_occupied,
        )
        return TemporalClosingSideResult(
            effective_mask,
            raw_result.right_closing_beams,
            raw_result.left_closing_beams,
            raw_result.right_occupied,
            raw_result.left_occupied,
            raw_result.rotation_gated,
        )

    def _bc_temporal_closing_side_telemetry(
        self,
        before: np.ndarray[Any, np.dtype[np.bool_]],
        result: TemporalClosingSideResult,
        *,
        angular_speed_radps: float,
    ) -> str:
        """Record measured beam counts, thresholds, and mask intersection."""

        config = self._bc_closing_side_config
        if result.rotation_gated:
            mode = "rotation_gated"
        elif result.right_occupied and result.left_occupied:
            mode = "both_occupied"
        elif result.right_occupied:
            mode = "right_occupied"
        elif result.left_occupied:
            mode = "left_occupied"
        else:
            mode = "clear"
        return (
            f"bc_closing_side={mode} "
            f"right_beams={result.right_closing_beams} left_beams={result.left_closing_beams} "
            f"minimum_beams={config.minimum_closing_beams} "
            f"sector_deg={config.sector_min_degrees:.1f}:{config.sector_max_degrees:.1f} "
            f"delta_m={config.closing_delta_m:.3f} "
            f"maximum_range_m={config.maximum_current_range_m:.3f} "
            f"angular_speed_radps={angular_speed_radps:.3f} "
            f"angular_gate_radps={config.maximum_angular_speed_radps:.3f} "
            f"raw_right={int(result.right_occupied)} raw_left={int(result.left_occupied)} "
            f"latched_right={int(self._bc_closing_side_latch.right_occupied)} "
            f"latched_left={int(self._bc_closing_side_latch.left_occupied)} "
            f"pre={','.join(map(str, np.flatnonzero(before)))} "
            f"post={','.join(map(str, np.flatnonzero(result.mask)))}"
        )

    def _bc_recurrent_escape_telemetry(
        self,
        before: np.ndarray[Any, np.dtype[np.bool_]],
        after: np.ndarray[Any, np.dtype[np.bool_]],
        *,
        pose: Pose2D,
        path_heading_rad: float,
    ) -> str:
        """Describe an active recurrent-escape constraint for episode logs."""

        recovery_count = self._machine.consecutive_recoveries
        threshold = self._integer("bc_recurrent_escape_after_recoveries")
        if not self._bc_yield_latch.latched or recovery_count < threshold:
            return ""
        before_ids = np.flatnonzero(before).tolist()
        after_ids = np.flatnonzero(after).tolist()
        minimum_lateral_displacement_m = self._float(
            "recurrent_escape_minimum_lateral_displacement_m"
        )
        lateral_ids = recurrent_yield_lateral_action_ids(
            pose=pose,
            path_heading_rad=path_heading_rad,
            minimum_lateral_displacement_m=minimum_lateral_displacement_m,
        )
        escape_ids = {*lateral_ids, REPLAN_ACTION_ID}
        if not np.array_equal(before, after):
            mode = "applied"
        elif any(action_id in escape_ids for action_id in after_ids):
            mode = "already_escape_only"
        else:
            mode = "unavailable"
        return (
            f"bc_recurrent_escape={mode} count={recovery_count} "
            f"minimum_lateral_m={minimum_lateral_displacement_m:.3f} "
            f"lateral_ids={','.join(map(str, lateral_ids))} "
            f"pre={','.join(map(str, before_ids))} final={','.join(map(str, after_ids))}"
        )

    def _select_decision(
        self,
        observation: RecoveryObservation,
        pose: Pose2D,
        failure: FailurePrediction,
        *,
        stalled_rejoin: bool = False,
    ) -> CoreRecoveryDecision:
        recurrent_escape_telemetry = ""
        directional_yield_telemetry = ""
        closing_side_telemetry = ""
        side_commitment_telemetry = ""
        if self._policy_type == "expert":
            try:
                return self._expert_decision(pose, failure)
            except (RuntimeError, ValueError) as error:
                self.get_logger().error(f"privileged expert failed safely: {error}")
                return CoreRecoveryDecision(WAIT_ACTION_ID, 0.0, "oracle_error_wait")
        mask = self._action_mask(pose, collision_risk=failure.collision_risk)
        if self._policy_type == "bc":
            path_heading_rad = self._task_path_heading(pose)
            distance_to_goal_m = float(observation.goal_polar[0])
            side_commitment_progress_m = self._bc_lateral_side_commitment.maximum_progress_m
            self._bc_lateral_side_commitment.update(
                distance_to_goal_m=distance_to_goal_m,
                path_heading_rad=path_heading_rad,
            )
            self._update_bc_progress_budget(float(observation.goal_polar[0]))
            # Observe every learned decision so the cap is relative to the
            # furthest task progress achieved, not to a retreating local cycle.
            self._bc_retreat_guard.observe(pose)
            mask = constrain_rejoin_actions(
                mask,
                collision_risk=failure.collision_risk,
                release_threshold=self._float("bc_rejoin_block_threshold"),
            )
            if self._bc_yield_latch.latched:
                pre_directional_yield_mask = mask.copy()
                mask = constrain_directional_yield_motion(
                    mask,
                    pose=pose,
                    path_heading_rad=path_heading_rad,
                    backup_distance_m=self._float("backup_mask_validated_distance_m"),
                    maximum_forward_progress_m=self._float("bc_yield_maximum_forward_progress_m"),
                )
                directional_yield_telemetry = (
                    "bc_yield_mask=active "
                    f"pre={','.join(map(str, np.flatnonzero(pre_directional_yield_mask)))} "
                    f"post={','.join(map(str, np.flatnonzero(mask)))}"
                )
                pre_closing_side_mask = mask.copy()
                closing_side_result = self._constrain_bc_temporal_closing_side(
                    mask,
                    observation,
                    pose=pose,
                    path_heading_rad=path_heading_rad,
                )
                mask = closing_side_result.mask
                closing_side_telemetry = self._bc_temporal_closing_side_telemetry(
                    pre_closing_side_mask,
                    closing_side_result,
                    angular_speed_radps=float(observation.robot_velocity[1]),
                )
                pre_near_field_mask = mask.copy()
                mask = constrain_near_field_subgoal_radius(
                    mask,
                    nearest_clearance_m=self._nearest_clearance(),
                    activation_clearance_m=self._float(
                        "bc_near_field_radius_activation_clearance_m"
                    ),
                    maximum_radius_m=self._float("bc_near_field_max_subgoal_radius_m"),
                )
                if not np.array_equal(pre_near_field_mask, mask):
                    closing_side_telemetry += (
                        "; bc_near_field_radius=applied "
                        f"clearance_m={self._nearest_clearance():.3f} "
                        f"maximum_radius_m={self._float('bc_near_field_max_subgoal_radius_m'):.3f} "
                        f"pre={','.join(map(str, np.flatnonzero(pre_near_field_mask)))} "
                        f"post={','.join(map(str, np.flatnonzero(mask)))}"
                    )
                pre_side_commitment_mask = mask.copy()
                mask = constrain_committed_lateral_side(
                    mask,
                    committed_side=self._bc_lateral_side_commitment.side,
                    pose=pose,
                    path_heading_rad=path_heading_rad,
                    minimum_lateral_displacement_m=self._float(
                        "recurrent_escape_minimum_lateral_displacement_m"
                    ),
                )
                if self._bc_lateral_side_commitment.active:
                    side_commitment_telemetry = (
                        f"bc_side_commitment={self._bc_lateral_side_commitment.side_name} "
                        f"progress_window_m={side_commitment_progress_m:.3f} "
                        f"pre={','.join(map(str, np.flatnonzero(pre_side_commitment_mask)))} "
                        f"post={','.join(map(str, np.flatnonzero(mask)))}"
                    )
            mask = constrain_stalled_rejoin(mask, escape_required=stalled_rejoin)
            mask = constrain_stalled_subgoals(
                mask,
                escape_required=self._bc_subgoal_stall_guard.escape_required,
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
            mask = constrain_net_retreat(
                mask,
                guard=self._bc_retreat_guard,
                pose=pose,
                backup_distance_m=self._float("backup_mask_validated_distance_m"),
            )
            # WAIT is budgeted only after every other bound has determined
            # which escape actions remain genuinely executable.  Otherwise a
            # later retreat/repetition constraint could remove the apparent
            # escape and leave the learned policy with an empty mask.
            bc_wait_budget = self._integer("bc_wait_budget_decisions")
            mask = constrain_stalled_wait(
                mask,
                consecutive_waits=self._bc_waits_without_progress,
                wait_budget=bc_wait_budget,
            )
            # Escalate only after every ordinary planning and repetition bound
            # has determined which lateral/replan actions remain legal.  The
            # constraint intersects that final mask and returns it unchanged
            # when no such escape exists, preserving the safe fallback set.
            pre_recurrent_escape_mask = mask.copy()
            mask = self._constrain_bc_recurrent_escape(
                mask,
                pose=pose,
                path_heading_rad=path_heading_rad,
            )
            recurrent_escape_telemetry = self._bc_recurrent_escape_telemetry(
                pre_recurrent_escape_mask,
                mask,
                pose=pose,
                path_heading_rad=path_heading_rad,
            )
        # Fail closed after composing all independent restrictions.  WAIT is
        # the sole fallback; this must never re-authorize translation.
        mask = ensure_safe_wait_fallback(mask)
        decision = self._policy.select_action(observation, mask)
        if self._policy_type == "bc":
            if self._bc_yield_latch.latched and self._bc_lateral_side_commitment.commit_action(
                decision.action_id,
                pose=pose,
                path_heading_rad=path_heading_rad,
                distance_to_goal_m=distance_to_goal_m,
                minimum_lateral_displacement_m=self._float(
                    "recurrent_escape_minimum_lateral_displacement_m"
                ),
            ):
                side_commitment_telemetry = (
                    f"bc_side_commitment=set_{self._bc_lateral_side_commitment.side_name} "
                    f"progress_window_m={side_commitment_progress_m:.3f}"
                )
            if decision.action_id == WAIT_ACTION_ID:
                self._bc_waits_without_progress += 1
            elif decision.action_id == BACKUP_ACTION_ID:
                self._bc_backups_without_progress += 1
            elif decision.action_id == REPLAN_ACTION_ID:
                self._bc_replans_without_progress += 1
            self._bc_subgoal_stall_guard.observe_decision(decision.action_id, pose)
            constraint_telemetry = "; ".join(
                item
                for item in (
                    directional_yield_telemetry,
                    closing_side_telemetry,
                    side_commitment_telemetry,
                    recurrent_escape_telemetry,
                )
                if item
            )
            if constraint_telemetry:
                decision = CoreRecoveryDecision(
                    decision.action_id,
                    decision.confidence,
                    f"{constraint_telemetry}; {decision.reason}",
                )
        return decision

    def _update_bc_progress_budget(self, distance_to_goal_m: float) -> None:
        """Reset learned-option budgets only after cumulative task progress."""
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
        self._bc_subgoal_stall_guard.reset()

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
            return self._bc_subgoal_option.is_complete(
                elapsed_s=elapsed,
                planner_succeeded=self._adapter.get_status() is PlannerStatus.SUCCEEDED,
            )
        return self._adapter.get_status() is PlannerStatus.SUCCEEDED

    def _execute(self, action_id: int, now_s: float) -> Pose2D | None:
        self._active_action = action_id
        self._action_started_s = now_s
        self._backup_start_clearance_m = (
            self._observable_nearest_clearance() if action_id == BACKUP_ACTION_ID else None
        )
        action = ACTIONS[action_id]
        if action.kind is RecoveryActionKind.SUBGOAL:
            pose = self._world_pose()
            temporary = action.target_pose(pose)
            assert temporary is not None
            temporary = orient_subgoal_for_rejoin(
                temporary,
                path_heading_rad=self._task_path_heading(pose),
            )
            self._adapter.set_recovery_goal(temporary)
            self._goal_preempted = True
            return temporary
        if action_id in {REPLAN_ACTION_ID, CONTINUE_ACTION_ID}:
            self._goal_preempted = not self._adapter.restore_original_goal()
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

    def _publish_terminal_transition(
        self,
        transition: StateTransition,
        confidence: float,
    ) -> bool:
        """Publish terminal state and reason before any source-state-specific branch."""

        if not transition.changed or transition.current not in {
            RecoveryState.FAILED,
            RecoveryState.SUCCEEDED,
        }:
            return False
        self._bc_closing_side_latch.reset()
        self._bc_lateral_side_commitment.reset()
        self._oracle_yield.reset()
        self._published_emergency_mode = None
        self._publish_decision(CONTINUE_ACTION_ID, confidence, transition.reason)
        return True

    def _decision_step(self) -> None:
        if not self._armed or self._odom is None or self._scan is None or not self._lidar_stack:
            return
        now_s = self.get_clock().now().nanoseconds * 1.0e-9
        if now_s - self._armed_at_s < self._float("arming_grace_s"):
            return
        pose = self._world_pose()
        failure = self._effective_failure(pose)
        task_forward_clearance: float | None = None
        bc_yield_active = False
        if self._policy_type == "bc":
            task_forward_clearance = self._task_forward_clearance(pose)
            scan_observation_id = int(self._scan.header.stamp.sec) * 1_000_000_000 + int(
                self._scan.header.stamp.nanosec
            )
            bc_yield_active = self._bc_yield_latch.update(
                collision_risk=failure.collision_risk,
                forward_clearance_m=task_forward_clearance,
                observation_id=scan_observation_id,
            )
            if not bc_yield_active:
                self._bc_closing_side_latch.reset()
        control_failure = failure
        if bc_yield_active:
            control_failure = FailurePrediction(
                collision_risk=1.0,
                freeze=failure.freeze,
                oscillation=failure.oscillation,
                deadlock=failure.deadlock,
            )
        distance = math.dist((pose.x, pose.y), (self._goal.x, self._goal.y))
        meaningful_progress = self._sequence_progress_budget.progress_reached(distance)
        linear_velocity = float(self._odom.twist.twist.linear.x)
        stop = self._motion_stop_distance(linear_velocity)
        motion_clearance = self._motion_clearance(linear_velocity)
        nearest_clearance = self._nearest_clearance()
        self._collision_safety_latched = update_collision_safety_latch(
            latched=self._collision_safety_latched,
            collision_risk=failure.collision_risk,
            trigger_threshold=self._float("bc_rejoin_block_threshold"),
            # Release the dynamic latch from the same commanded-motion sector
            # that triggered it. A static side wall remains protected by the
            # independent omnidirectional footprint guard below, but cannot
            # impersonate an approaching actor after that actor has cleared.
            footprint_clearance_m=motion_clearance,
            release_clearance_m=(
                self._float("collision_latched_stop_clearance_m")
                + self._float("emergency_release_hysteresis_m")
            ),
        )
        footprint_stop = self._footprint_stop_distance(linear_velocity)
        footprint_hazard = nearest_clearance < footprint_stop
        raw_emergency = emergency_hazard_with_hysteresis(
            emergency_active=self._emergency,
            motion_clearance_m=motion_clearance,
            motion_stop_distance_m=stop,
            footprint_clearance_m=nearest_clearance,
            footprint_stop_distance_m=footprint_stop,
            release_hysteresis_m=self._float("emergency_release_hysteresis_m"),
            footprint_release_hysteresis_m=self._float("footprint_release_hysteresis_m"),
        )
        rear_clearance = self._observed_laser_clearance(math.pi)
        nearest_angle = self._nearest_obstacle_angle()
        emergency_backup_permitted = self._footprint_backup_permitted(footprint_hazard)
        if self._policy_type == "bc":
            emergency_backup_permitted &= self._bc_retreat_guard.backup_permitted(
                pose,
                backup_distance_m=(
                    self._float("backup_speed_mps") * self._float("emergency_backup_duration_s")
                ),
            )
        self._emergency, self._emergency_escape_mode = self._emergency_escape.update(
            now_s=now_s,
            hazard=raw_emergency,
            linear_speed_mps=float(self._odom.twist.twist.linear.x),
            rear_clearance_m=0.0 if rear_clearance is None else rear_clearance,
            backup_permitted=emergency_backup_permitted,
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
            failure_score=control_failure.score,
            tau_off=self._machine.config.tau_off,
            option_elapsed_s=now_s - self._machine.state_since_s,
            maximum_option_duration_s=(
                self._machine.config.maximum_extended_recovery_duration_s
                if self._oracle_yield.active or bc_yield_active
                else self._machine.config.maximum_recovery_duration_s
            ),
        )
        transition = self._machine.update(
            StateMachineInput(
                now_s=now_s,
                failure_score=control_failure.score,
                valid_progress=self._valid_progress(),
                meaningful_progress=meaningful_progress,
                original_goal_active=not self._goal_preempted,
                emergency_stop=self._emergency,
                goal_reached=distance <= self._float("goal_tolerance_m"),
                recovery_action_complete=action_complete and not persistent_failure_followup,
                recovery_option_active=self._oracle_yield.active or bc_yield_active,
            )
        )
        if meaningful_progress and (
            transition.previous in {RecoveryState.NORMAL, RecoveryState.PENDING_RECOVERY}
            or transition.reason == "original_goal_restored"
        ):
            self._sequence_progress_budget.acknowledge(distance)
        if transition.current is not RecoveryState.RECOVERY:
            self._backup_start_clearance_m = None
        if self._publish_terminal_transition(transition, failure.score):
            return
        if transition.current is RecoveryState.RECOVERY and (
            transition.changed or persistent_failure_followup
        ):
            observation = self._observation(control_failure)
            decision_failure = control_failure
            if self._collision_safety_latched and control_failure.collision_risk < self._float(
                "bc_rejoin_block_threshold"
            ):
                decision_failure = FailurePrediction(
                    collision_risk=self._float("bc_rejoin_block_threshold"),
                    freeze=control_failure.freeze,
                    oscillation=control_failure.oscillation,
                    deadlock=control_failure.deadlock,
                )
            decision = self._select_decision(
                observation,
                pose,
                decision_failure,
                stalled_rejoin=transition.reason == "rejoin_failure_retry",
            )
            temporary = self._execute(decision.action_id, now_s)
            if bc_yield_active:
                clearance_text = (
                    "unobserved"
                    if task_forward_clearance is None
                    else f"{task_forward_clearance:.3f}"
                )
                decision = CoreRecoveryDecision(
                    decision.action_id,
                    decision.confidence,
                    (
                        "bc_directional_yield=active "
                        f"forward_clearance_m={clearance_text} "
                        f"clear_frames={self._bc_yield_latch.clear_frames}; {decision.reason}"
                    ),
                )
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
            linear_velocity = float(self._odom.twist.twist.linear.x)
            stop = self._motion_stop_distance(linear_velocity)
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
            # The decision timer bounds and re-evaluates each turn pulse.  The
            # faster control loop independently stops the sweep as soon as the
            # same omnidirectional footprint margin becomes unsafe.
            if self._nearest_clearance() >= self._effective_emergency_rotation_clearance():
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
