"""Configurable ROS2 episode logger writing one JSONL stream per episode."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import PoseArray, PoseStamped, Twist
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMessage
from ramp_core.data.schema import EpisodeMetadata, EpisodeOutcome, NavigationStep
from ramp_core.evaluation.navigation import (
    ConsecutiveEvidenceTracker,
    PlannerAbortTracker,
    navigation_status_is_active,
    timeout_is_invalid_reset,
)
from ramp_core.geometry import point_to_oriented_box_distance
from ramp_core.planning.online import sanitize_near_field_returns
from ramp_msgs.msg import FailureStatus, RecoveryDecision
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _resample_lidar(
    message: LaserScan,
    beam_count: int = 180,
    bilateral_edge_self_return_max_m: float = 0.0,
) -> np.ndarray[Any, np.dtype[np.float32]]:
    source = sanitize_near_field_returns(
        message.ranges,
        minimum_valid_range_m=0.0,
        bilateral_edge_self_return_max_m=bilateral_edge_self_return_max_m,
    ).astype(np.float32)
    if source.size == 0:
        raise ValueError("received an empty LaserScan")
    maximum = float(message.range_max) if message.range_max > 0.0 else 30.0
    source = np.nan_to_num(source, nan=maximum, posinf=maximum, neginf=0.0)
    source = np.clip(source, 0.0, maximum)
    coordinates = np.linspace(0.0, source.size - 1.0, beam_count)
    return np.interp(coordinates, np.arange(source.size), source).astype(np.float32)


def _parse_shelf_boxes(payload: str) -> tuple[tuple[float, float, float, float, float], ...]:
    """Parse scenario shelf poses into exact 2-D bounding boxes."""
    obstacles = json.loads(payload)
    if not isinstance(obstacles, list):
        raise ValueError("static_obstacles_json must contain a list")
    boxes: list[tuple[float, float, float, float, float]] = []
    for obstacle in obstacles:
        if not isinstance(obstacle, dict) or obstacle.get("model") != "shelf":
            raise ValueError("physical static collision currently supports only shelf models")
        position = obstacle.get("pos")
        if not isinstance(position, list) or len(position) < 2:
            raise ValueError("static shelf requires a position")
        yaw = float(position[2]) if len(position) > 2 else 0.0
        # shelf_static.sdf spans x +/-0.45 and local y [-0.395, 0.005].
        center_x = float(position[0]) + 0.195 * math.sin(yaw)
        center_y = float(position[1]) - 0.195 * math.cos(yaw)
        boxes.append((center_x, center_y, 0.45, 0.20, yaw))
    return tuple(boxes)


class EpisodeLoggerNode(Node):
    def __init__(self) -> None:
        super().__init__("episode_logger")
        self.declare_parameter("episode_id", "")
        self.declare_parameter("scenario_id", "")
        self.declare_parameter("map_id", "map_empty")
        self.declare_parameter("seed", 0)
        self.declare_parameter("split", "train")
        self.declare_parameter("planner_id", "dwb")
        self.declare_parameter("source_policy", "base")
        self.declare_parameter("arena_commit", "unknown")
        self.declare_parameter("project_commit", "unknown")
        self.declare_parameter("output_directory", "data/raw")
        self.declare_parameter("sample_frequency_hz", 10.0)
        self.declare_parameter("episode_timeout_s", 180.0)
        self.declare_parameter("planner_startup_failure_s", 12.0)
        self.declare_parameter("wait_for_navigation_active", False)
        self.declare_parameter("navigation_activation_timeout_s", 20.0)
        self.declare_parameter("navigation_activation_wall_timeout_s", 90.0)
        self.declare_parameter("terminate_on_planner_abort", False)
        self.declare_parameter("planner_abort_grace_s", 5.0)
        self.declare_parameter("goal_x", 0.0)
        self.declare_parameter("goal_y", 0.0)
        self.declare_parameter("goal_yaw", 0.0)
        self.declare_parameter("goal_tolerance_m", 0.25)
        self.declare_parameter("physical_goal_tolerance_m", 0.30)
        self.declare_parameter("goal_confirmation_timeout_s", 1.0)
        self.declare_parameter("robot_start_x", 0.0)
        self.declare_parameter("robot_start_y", 0.0)
        self.declare_parameter("robot_start_yaw", 0.0)
        self.declare_parameter("odometry_is_world_frame", False)
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("scan_topic", "scan")
        self.declare_parameter("cmd_vel_topic", "cmd_vel")
        self.declare_parameter("base_cmd_vel_topic", "cmd_vel")
        self.declare_parameter("global_path_topic", "plan")
        self.declare_parameter("nav_status_topic", "navigate_to_pose/_action/status")
        self.declare_parameter("collision_topic", "collision")
        self.declare_parameter("failure_status_topic", "failure_status")
        self.declare_parameter("recovery_decision_topic", "recovery_decision")
        self.declare_parameter("privileged_humans_topic", "/ramp/privileged/humans")
        self.declare_parameter("privileged_robot_pose_topic", "/ramp/privileged/robot_pose")
        self.declare_parameter("maximum_privileged_pose_jump_m", 1.0)
        self.declare_parameter("actor_health_topic", "/ramp/actors_healthy")
        self.declare_parameter("episode_start_topic", "/ramp/episode_started")
        self.declare_parameter("logger_ready_topic", "/ramp/logger_ready")
        self.declare_parameter("robot_radius_m", 0.36)
        self.declare_parameter("human_radius_m", 0.35)
        self.declare_parameter("lidar_collision_distance_m", 0.12)
        self.declare_parameter("lidar_collision_confirmation_frames", 3)
        self.declare_parameter("lidar_static_collision_enabled", True)
        self.declare_parameter("bilateral_edge_self_return_max_m", 0.34)
        self.declare_parameter("physical_static_collision_enabled", False)
        self.declare_parameter("static_obstacles_json", "[]")

        episode_id = self._string_parameter("episode_id")
        scenario_id = self._string_parameter("scenario_id")
        if not episode_id or not scenario_id:
            raise ValueError("episode_id and scenario_id parameters are required")
        output_directory = Path(self._string_parameter("output_directory")).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
        self._static_boxes = _parse_shelf_boxes(
            str(self.get_parameter("static_obstacles_json").value)
        )
        self._stream_path = output_directory / f"{episode_id}.jsonl"
        self._metadata_path = output_directory / f"{episode_id}.metadata.json"
        self._outcome_path = output_directory / f"{episode_id}.outcome.json"
        self._stream = self._stream_path.open("x", encoding="utf-8", buffering=1)
        self._metadata = EpisodeMetadata(
            episode_id=episode_id,
            scenario_id=scenario_id,
            map_id=self._string_parameter("map_id"),
            seed=int(self.get_parameter("seed").value),
            split=self._string_parameter("split"),
            planner_id=self._string_parameter("planner_id"),
            source_policy=self._string_parameter("source_policy"),
            arena_commit=self._string_parameter("arena_commit"),
            project_commit=self._string_parameter("project_commit"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._metadata_path.write_text(
            json.dumps(
                {
                    name: getattr(self._metadata, name)
                    for name in self._metadata.__dataclass_fields__
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self._goal = np.asarray(
            [
                float(self.get_parameter("goal_x").value),
                float(self.get_parameter("goal_y").value),
                float(self.get_parameter("goal_yaw").value),
            ],
            dtype=np.float32,
        )
        self._robot_start = np.asarray(
            [
                float(self.get_parameter("robot_start_x").value),
                float(self.get_parameter("robot_start_y").value),
                float(self.get_parameter("robot_start_yaw").value),
            ],
            dtype=np.float32,
        )
        self._timeout = float(self.get_parameter("episode_timeout_s").value)
        self._goal_tolerance = float(self.get_parameter("goal_tolerance_m").value)
        self._wait_for_navigation_active = bool(
            self.get_parameter("wait_for_navigation_active").value
        )
        self._episode_started = not self._wait_for_navigation_active
        self._navigation_activation_timeout = float(
            self.get_parameter("navigation_activation_timeout_s").value
        )
        self._navigation_activation_wall_timeout = float(
            self.get_parameter("navigation_activation_wall_timeout_s").value
        )
        if self._navigation_activation_timeout <= 0.0:
            raise ValueError("navigation_activation_timeout_s must be positive")
        if self._navigation_activation_wall_timeout <= 0.0:
            raise ValueError("navigation_activation_wall_timeout_s must be positive")
        self._activation_wait_start_time: float | None = None
        self._ready_publisher = self.create_publisher(
            Bool, self._string_parameter("logger_ready_topic"), 10
        )
        self._start_time: float | None = None
        self._last_sample_timestamp: float | None = None
        self._initial_robot_position: tuple[float, float] | None = None
        self._maximum_start_displacement = 0.0
        self._outcome: EpisodeOutcome | None = None
        self._outcome_detail = ""
        self._pending_goal_detail: str | None = None
        self._pending_goal_start_wall_s: float | None = None
        self._odom: Odometry | None = None
        self._lidar: np.ndarray[Any, np.dtype[np.float32]] | None = None
        self._cmd = np.zeros(2, dtype=np.float32)
        self._base_cmd = np.zeros(2, dtype=np.float32)
        self._path: tuple[tuple[float, float], ...] = ()
        self._planner_status = int(GoalStatus.STATUS_UNKNOWN)
        self._planner_statuses: tuple[int, ...] = ()
        self._planner_ever_active = False
        self._planner_abort_tracker = PlannerAbortTracker(
            grace_s=float(self.get_parameter("planner_abort_grace_s").value)
        )
        self._lidar_collision_tracker = ConsecutiveEvidenceTracker(
            confirmation_frames=int(self.get_parameter("lidar_collision_confirmation_frames").value)
        )
        self._failure_prediction = np.zeros(4, dtype=np.float32)
        self._failure_score = 0.0
        self._recovery_state = 0
        self._recovery_action = 24
        self._recovery_reason = "not_triggered"
        self._collision = False
        self._human_positions: tuple[tuple[float, float], ...] = ()
        self._privileged_robot_pose: tuple[float, float, float] | None = None
        self._sample_count = 0
        self._readiness_warning_count = 0
        self._subscription_handles: list[Any] = []
        self._subscribe()
        frequency = float(self.get_parameter("sample_frequency_hz").value)
        if frequency <= 0.0:
            raise ValueError("sample_frequency_hz must be positive")
        self._wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._activation_wait_start_wall_s = self._wall_clock.now().nanoseconds * 1.0e-9
        self._sample_timer = self.create_timer(
            1.0 / frequency, self._sample, clock=self._wall_clock
        )

    def _string_parameter(self, name: str) -> str:
        return str(self.get_parameter(name).value)

    def _subscribe(self) -> None:
        self._subscription_handles.extend(
            [
                self.create_subscription(
                    Odometry,
                    self._string_parameter("odom_topic"),
                    self._on_odom,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    LaserScan,
                    self._string_parameter("scan_topic"),
                    self._on_scan,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    Twist, self._string_parameter("cmd_vel_topic"), self._on_cmd, 10
                ),
                self.create_subscription(
                    Twist,
                    self._string_parameter("base_cmd_vel_topic"),
                    self._on_base_cmd,
                    10,
                ),
                self.create_subscription(
                    PathMessage,
                    self._string_parameter("global_path_topic"),
                    self._on_path,
                    10,
                ),
                self.create_subscription(
                    GoalStatusArray,
                    self._string_parameter("nav_status_topic"),
                    self._on_status,
                    10,
                ),
                self.create_subscription(
                    Bool, self._string_parameter("collision_topic"), self._on_collision, 10
                ),
                self.create_subscription(
                    FailureStatus,
                    self._string_parameter("failure_status_topic"),
                    self._on_failure,
                    10,
                ),
                self.create_subscription(
                    RecoveryDecision,
                    self._string_parameter("recovery_decision_topic"),
                    self._on_recovery,
                    10,
                ),
                self.create_subscription(
                    PoseArray,
                    self._string_parameter("privileged_humans_topic"),
                    self._on_humans,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    PoseStamped,
                    self._string_parameter("privileged_robot_pose_topic"),
                    self._on_privileged_robot_pose,
                    qos_profile_sensor_data,
                ),
                self.create_subscription(
                    Bool,
                    self._string_parameter("actor_health_topic"),
                    self._on_actor_health,
                    10,
                ),
                self.create_subscription(
                    Bool,
                    self._string_parameter("episode_start_topic"),
                    self._on_episode_start,
                    10,
                ),
            ]
        )

    def _on_odom(self, message: Odometry) -> None:
        self._odom = message

    def _on_scan(self, message: LaserScan) -> None:
        try:
            self._lidar = _resample_lidar(
                message,
                bilateral_edge_self_return_max_m=float(
                    self.get_parameter("bilateral_edge_self_return_max_m").value
                ),
            )
        except ValueError as error:
            self.get_logger().warning(str(error))

    def _on_cmd(self, message: Twist) -> None:
        self._cmd[:] = message.linear.x, message.angular.z

    def _on_base_cmd(self, message: Twist) -> None:
        self._base_cmd[:] = message.linear.x, message.angular.z

    def _on_path(self, message: PathMessage) -> None:
        frame = message.header.frame_id.rstrip("/")
        if frame.endswith("odom") and not bool(self.get_parameter("odometry_is_world_frame").value):
            start_yaw = float(self._robot_start[2])
            cosine = math.cos(start_yaw)
            sine = math.sin(start_yaw)
            self._path = tuple(
                (
                    float(self._robot_start[0])
                    + cosine * pose.pose.position.x
                    - sine * pose.pose.position.y,
                    float(self._robot_start[1])
                    + sine * pose.pose.position.x
                    + cosine * pose.pose.position.y,
                )
                for pose in message.poses
            )
        else:
            self._path = tuple(
                (pose.pose.position.x, pose.pose.position.y) for pose in message.poses
            )

    def _on_status(self, message: GoalStatusArray) -> None:
        if not message.status_list:
            return
        raw_statuses = [int(item.status) for item in message.status_list]
        self._planner_statuses = tuple(raw_statuses)
        self._planner_ever_active |= navigation_status_is_active(
            tuple(raw_statuses),
            accepted=int(GoalStatus.STATUS_ACCEPTED),
            executing=int(GoalStatus.STATUS_EXECUTING),
            canceling=int(GoalStatus.STATUS_CANCELING),
        )
        active = {
            int(GoalStatus.STATUS_ACCEPTED),
            int(GoalStatus.STATUS_EXECUTING),
            int(GoalStatus.STATUS_CANCELING),
        }
        status = next((item for item in raw_statuses if item in active), raw_statuses[-1])
        self._planner_status = status
        if status == GoalStatus.STATUS_SUCCEEDED and self._odom is not None:
            self._confirm_goal_reached("original NavigateToPose succeeded")

    def _on_collision(self, message: Bool) -> None:
        self._collision = bool(message.data)
        if self._collision:
            self._set_outcome(EpisodeOutcome.COLLISION, "collision topic asserted")

    def _on_failure(self, message: FailureStatus) -> None:
        self._failure_prediction[:] = (
            message.collision_risk,
            message.freeze,
            message.oscillation,
            message.deadlock,
        )
        self._failure_score = float(message.failure_score)

    def _on_recovery(self, message: RecoveryDecision) -> None:
        self._recovery_action = int(message.action_id)
        self._recovery_state = int(message.recovery_state)
        self._recovery_reason = str(message.reason)
        if self._recovery_state == RecoveryDecision.SUCCEEDED and self._odom is not None:
            self._confirm_goal_reached("recovery manager succeeded with goal-distance verification")
        elif self._recovery_state == RecoveryDecision.FAILED:
            self._set_outcome(
                EpisodeOutcome.PLANNER_FAILURE,
                "recovery manager exhausted the configured recovery attempts",
            )

    def _on_humans(self, message: PoseArray) -> None:
        self._human_positions = tuple((pose.position.x, pose.position.y) for pose in message.poses)

    def _on_privileged_robot_pose(self, message: PoseStamped) -> None:
        pose = message.pose
        new_pose = (
            float(pose.position.x),
            float(pose.position.y),
            _yaw_from_quaternion(
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            ),
        )
        if (
            self._episode_started
            and self._privileged_robot_pose is not None
            and math.dist(new_pose[:2], self._privileged_robot_pose[:2])
            > float(self.get_parameter("maximum_privileged_pose_jump_m").value)
        ):
            self._set_outcome(
                EpisodeOutcome.INVALID_RESET,
                "Gazebo robot pose jumped during the active episode",
            )
        self._privileged_robot_pose = new_pose
        if self._pending_goal_detail is not None:
            self._confirm_goal_reached(self._pending_goal_detail)

    def _on_actor_health(self, message: Bool) -> None:
        if not bool(message.data):
            self._set_outcome(
                EpisodeOutcome.SIMULATOR_FAILURE,
                "Gazebo rejected a deterministic pedestrian proxy pose update",
            )

    def _on_episode_start(self, message: Bool) -> None:
        self._episode_started |= bool(message.data)

    def _set_outcome(self, outcome: EpisodeOutcome, detail: str) -> None:
        if self._outcome is None:
            self._outcome = outcome
            self._outcome_detail = detail

    def _confirm_goal_reached(self, detail: str) -> None:
        if self._odom is None or self._privileged_robot_pose is None:
            return
        localized_pose = self._world_robot_pose(self._odom)
        if float(np.linalg.norm(self._goal[:2] - localized_pose[:2])) > self._goal_tolerance:
            return
        physical_distance = math.dist(self._goal[:2], self._privileged_robot_pose[:2])
        if physical_distance > float(self.get_parameter("physical_goal_tolerance_m").value):
            if self._pending_goal_detail is None:
                self._pending_goal_detail = detail
                self._pending_goal_start_wall_s = self._wall_clock.now().nanoseconds * 1.0e-9
            return
        self._set_outcome(EpisodeOutcome.GOAL_REACHED, detail)

    @property
    def terminal(self) -> bool:
        return self._outcome is not None

    def _world_robot_pose(self, odometry: Odometry) -> np.ndarray[Any, np.dtype[np.float32]]:
        pose = odometry.pose.pose
        yaw = _yaw_from_quaternion(
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        )
        if bool(self.get_parameter("odometry_is_world_frame").value):
            return np.asarray(
                [pose.position.x, pose.position.y, yaw],
                dtype=np.float32,
            )
        start_yaw = float(self._robot_start[2])
        return np.asarray(
            [
                self._robot_start[0]
                + math.cos(start_yaw) * pose.position.x
                - math.sin(start_yaw) * pose.position.y,
                self._robot_start[1]
                + math.sin(start_yaw) * pose.position.x
                + math.cos(start_yaw) * pose.position.y,
                math.atan2(math.sin(start_yaw + yaw), math.cos(start_yaw + yaw)),
            ],
            dtype=np.float32,
        )

    def _sample(self) -> None:
        if self._outcome is not None:
            return
        ready = Bool()
        ready.data = True
        self._ready_publisher.publish(ready)
        wall_now = self._wall_clock.now().nanoseconds * 1.0e-9
        if (
            self._pending_goal_start_wall_s is not None
            and wall_now - self._pending_goal_start_wall_s
            >= float(self.get_parameter("goal_confirmation_timeout_s").value)
        ):
            self._set_outcome(
                EpisodeOutcome.SIMULATOR_FAILURE,
                "localized goal success disagrees with Gazebo robot pose",
            )
            return
        if (
            self._wait_for_navigation_active
            and not self._episode_started
            and wall_now - self._activation_wait_start_wall_s
            >= self._navigation_activation_wall_timeout
        ):
            self._set_outcome(
                EpisodeOutcome.SIMULATOR_FAILURE,
                "episode start handshake did not complete before the wall-clock deadline",
            )
            return
        if self._odom is None or self._lidar is None:
            self._readiness_warning_count += 1
            if self._readiness_warning_count % 50 == 0:
                self.get_logger().warning(
                    f"waiting for inputs: odom={self._odom is not None} "
                    f"lidar={self._lidar is not None}"
                )
            return
        stamp = self._odom.header.stamp
        now = float(stamp.sec) + float(stamp.nanosec) * 1.0e-9
        if self._last_sample_timestamp is not None:
            if now < self._last_sample_timestamp:
                self._set_outcome(
                    EpisodeOutcome.INVALID_RESET,
                    "odometry simulation time moved backwards during episode",
                )
                return
            if now == self._last_sample_timestamp:
                return
        self._last_sample_timestamp = now
        if self._activation_wait_start_time is None:
            self._activation_wait_start_time = now
        if self._wait_for_navigation_active and not self._episode_started:
            if now - self._activation_wait_start_time >= self._navigation_activation_timeout:
                self._set_outcome(
                    EpisodeOutcome.INVALID_RESET,
                    "NavigateToPose did not activate within the startup deadline",
                )
            return
        if self._start_time is None:
            self._start_time = now
        elapsed = now - self._start_time
        if elapsed >= self._timeout:
            if timeout_is_invalid_reset(
                planner_ever_active=self._planner_ever_active,
                maximum_start_displacement_m=self._maximum_start_displacement,
            ):
                self._set_outcome(
                    EpisodeOutcome.INVALID_RESET,
                    "NavigateToPose never became active and robot never left its start",
                )
            else:
                self._set_outcome(EpisodeOutcome.TIMEOUT, "configured episode timeout")
            return
        if bool(self.get_parameter("terminate_on_planner_abort").value) and (
            self._planner_abort_tracker.update(
                statuses=self._planner_statuses,
                simulated_time_s=elapsed,
                accepted=int(GoalStatus.STATUS_ACCEPTED),
                executing=int(GoalStatus.STATUS_EXECUTING),
                canceling=int(GoalStatus.STATUS_CANCELING),
                aborted=int(GoalStatus.STATUS_ABORTED),
            )
        ):
            self._set_outcome(
                EpisodeOutcome.PLANNER_FAILURE,
                "NavigateToPose remained aborted without a replacement active goal",
            )
            return
        twist = self._odom.twist.twist
        robot_pose = self._world_robot_pose(self._odom)
        position = float(robot_pose[0]), float(robot_pose[1])
        if self._initial_robot_position is None:
            self._initial_robot_position = position
        else:
            self._maximum_start_displacement = max(
                self._maximum_start_displacement,
                math.dist(self._initial_robot_position, position),
            )
        if (
            elapsed >= float(self.get_parameter("planner_startup_failure_s").value)
            and self._maximum_start_displacement < 0.05
            and self._planner_status == GoalStatus.STATUS_ABORTED
        ):
            self._set_outcome(
                EpisodeOutcome.PLANNER_FAILURE,
                "Nav2 aborted before the robot produced startup movement",
            )
        distance = float(np.linalg.norm(self._goal[:2] - robot_pose[:2]))
        nearest_obstacle = float(np.min(self._lidar))
        privileged_robot_pose = self._privileged_robot_pose
        lidar_static_collision = bool(
            self.get_parameter("lidar_static_collision_enabled").value
        ) and nearest_obstacle <= float(self.get_parameter("lidar_collision_distance_m").value)
        if self._lidar_collision_tracker.update(lidar_static_collision):
            self._collision = True
            self._set_outcome(
                EpisodeOutcome.COLLISION,
                "LiDAR obstacle return lies inside the Jackal footprint",
            )
        if (
            bool(self.get_parameter("physical_static_collision_enabled").value)
            and privileged_robot_pose is not None
            and self._static_boxes
        ):
            static_clearance = min(
                point_to_oriented_box_distance(
                    privileged_robot_pose[:2],
                    (box[0], box[1]),
                    (box[2], box[3]),
                    box[4],
                )
                for box in self._static_boxes
            )
            if static_clearance <= float(self.get_parameter("robot_radius_m").value):
                self._collision = True
                self._set_outcome(
                    EpisodeOutcome.COLLISION,
                    "physical robot footprint intersects known static scenario geometry",
                )
        nearest_human = math.inf
        if self._human_positions and privileged_robot_pose is not None:
            nearest_human = min(
                math.dist(privileged_robot_pose[:2], human) for human in self._human_positions
            )
            collision_distance = float(self.get_parameter("robot_radius_m").value) + float(
                self.get_parameter("human_radius_m").value
            )
            if nearest_human <= collision_distance:
                self._collision = True
                self._set_outcome(EpisodeOutcome.COLLISION, "privileged robot-human overlap")
        step = NavigationStep(
            timestamp=elapsed,
            robot_pose=robot_pose,
            robot_velocity=np.asarray([twist.linear.x, twist.angular.z], dtype=np.float32),
            cmd_vel=self._cmd.copy(),
            base_cmd_vel=self._base_cmd.copy(),
            goal=self._goal,
            distance_to_goal=distance,
            global_path=self._path,
            lidar=self._lidar,
            nearest_obstacle_distance=nearest_obstacle,
            planner_status=self._planner_status,
            failure_prediction=self._failure_prediction.copy(),
            failure_score=self._failure_score,
            recovery_state=self._recovery_state,
            recovery_action=self._recovery_action,
            collision=self._collision,
            timeout=False,
            recovery_reason=self._recovery_reason,
            privileged={
                "human_positions": self._human_positions,
                "nearest_human_distance": nearest_human,
                "robot_pose": privileged_robot_pose,
            },
        )
        self._stream.write(json.dumps(step.as_jsonable(), separators=(",", ":")) + "\n")
        self._sample_count += 1
        if self._sample_count == 1:
            self.get_logger().info("recorded first synchronized odometry/LiDAR sample")

    def finalize(self) -> None:
        if self._stream.closed:
            return
        if self._outcome is None:
            self._set_outcome(
                EpisodeOutcome.SIMULATOR_FAILURE, "logger stopped without terminal event"
            )
        self._stream.flush()
        self._stream.close()
        localized_goal_distance: float | None = None
        if self._odom is not None:
            localized_goal_distance = float(
                np.linalg.norm(self._goal[:2] - self._world_robot_pose(self._odom)[:2])
            )
        physical_goal_distance = (
            math.dist(self._goal[:2], self._privileged_robot_pose[:2])
            if self._privileged_robot_pose is not None
            else None
        )
        payload = {
            "episode_id": self._metadata.episode_id,
            "outcome": self._outcome.name if self._outcome is not None else "SIMULATOR_FAILURE",
            "outcome_id": int(
                self._outcome if self._outcome is not None else EpisodeOutcome.SIMULATOR_FAILURE
            ),
            "detail": self._outcome_detail,
            "sample_count": self._sample_count,
            "localized_goal_distance_m": localized_goal_distance,
            "physical_goal_distance_m": physical_goal_distance,
        }
        self._outcome_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: EpisodeLoggerNode | None = None
    try:
        node = EpisodeLoggerNode()
        while rclpy.ok() and not node.terminal:
            rclpy.spin_once(node, timeout_sec=0.2)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        if node is not None:
            node.finalize()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
