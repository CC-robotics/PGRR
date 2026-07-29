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
from geometry_msgs.msg import PoseArray, Twist
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMessage
from ramp_core.data.schema import EpisodeMetadata, EpisodeOutcome, NavigationStep
from ramp_msgs.msg import FailureStatus, RecoveryDecision
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _resample_lidar(
    message: LaserScan, beam_count: int = 180
) -> np.ndarray[Any, np.dtype[np.float32]]:
    source = np.asarray(message.ranges, dtype=np.float32)
    if source.size == 0:
        raise ValueError("received an empty LaserScan")
    maximum = float(message.range_max) if message.range_max > 0.0 else 30.0
    source = np.nan_to_num(source, nan=maximum, posinf=maximum, neginf=0.0)
    source = np.clip(source, 0.0, maximum)
    coordinates = np.linspace(0.0, source.size - 1.0, beam_count)
    return np.interp(coordinates, np.arange(source.size), source).astype(np.float32)


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
        self.declare_parameter("goal_x", 0.0)
        self.declare_parameter("goal_y", 0.0)
        self.declare_parameter("goal_yaw", 0.0)
        self.declare_parameter("robot_start_x", 0.0)
        self.declare_parameter("robot_start_y", 0.0)
        self.declare_parameter("robot_start_yaw", 0.0)
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
        self.declare_parameter("robot_radius_m", 0.36)
        self.declare_parameter("human_radius_m", 0.35)

        episode_id = self._string_parameter("episode_id")
        scenario_id = self._string_parameter("scenario_id")
        if not episode_id or not scenario_id:
            raise ValueError("episode_id and scenario_id parameters are required")
        output_directory = Path(self._string_parameter("output_directory")).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
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
        self._start_time: float | None = None
        self._outcome: EpisodeOutcome | None = None
        self._outcome_detail = ""
        self._odom: Odometry | None = None
        self._lidar: np.ndarray[Any, np.dtype[np.float32]] | None = None
        self._cmd = np.zeros(2, dtype=np.float32)
        self._base_cmd = np.zeros(2, dtype=np.float32)
        self._path: tuple[tuple[float, float], ...] = ()
        self._planner_status = int(GoalStatus.STATUS_UNKNOWN)
        self._recovery_state = 0
        self._recovery_action = 24
        self._collision = False
        self._human_positions: tuple[tuple[float, float], ...] = ()
        self._sample_count = 0
        self._readiness_warning_count = 0
        self._subscription_handles: list[Any] = []
        self._subscribe()
        frequency = float(self.get_parameter("sample_frequency_hz").value)
        if frequency <= 0.0:
            raise ValueError("sample_frequency_hz must be positive")
        self._wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
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
            ]
        )

    def _on_odom(self, message: Odometry) -> None:
        self._odom = message

    def _on_scan(self, message: LaserScan) -> None:
        try:
            self._lidar = _resample_lidar(message)
        except ValueError as error:
            self.get_logger().warning(str(error))

    def _on_cmd(self, message: Twist) -> None:
        self._cmd[:] = message.linear.x, message.angular.z

    def _on_base_cmd(self, message: Twist) -> None:
        self._base_cmd[:] = message.linear.x, message.angular.z

    def _on_path(self, message: PathMessage) -> None:
        self._path = tuple((pose.pose.position.x, pose.pose.position.y) for pose in message.poses)

    def _on_status(self, message: GoalStatusArray) -> None:
        if not message.status_list:
            return
        status = int(message.status_list[-1].status)
        self._planner_status = status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._set_outcome(EpisodeOutcome.GOAL_REACHED, "NavigateToPose succeeded")

    def _on_collision(self, message: Bool) -> None:
        self._collision = bool(message.data)
        if self._collision:
            self._set_outcome(EpisodeOutcome.COLLISION, "collision topic asserted")

    def _on_failure(self, message: FailureStatus) -> None:
        self._recovery_state = 2 if message.triggered else 0

    def _on_recovery(self, message: RecoveryDecision) -> None:
        self._recovery_action = int(message.action_id)

    def _on_humans(self, message: PoseArray) -> None:
        self._human_positions = tuple((pose.position.x, pose.position.y) for pose in message.poses)

    def _set_outcome(self, outcome: EpisodeOutcome, detail: str) -> None:
        if self._outcome is None:
            self._outcome = outcome
            self._outcome_detail = detail

    @property
    def terminal(self) -> bool:
        return self._outcome is not None

    def _sample(self) -> None:
        if self._outcome is not None:
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
        if self._start_time is None:
            self._start_time = now
        elapsed = now - self._start_time
        if elapsed >= self._timeout:
            self._set_outcome(EpisodeOutcome.TIMEOUT, "configured episode timeout")
            return
        pose = self._odom.pose.pose
        twist = self._odom.twist.twist
        yaw = _yaw_from_quaternion(
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        )
        start_yaw = float(self._robot_start[2])
        robot_pose = np.asarray(
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
        distance = float(np.linalg.norm(self._goal[:2] - robot_pose[:2]))
        nearest_human = math.inf
        if self._human_positions:
            nearest_human = min(
                math.dist((float(robot_pose[0]), float(robot_pose[1])), human)
                for human in self._human_positions
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
            nearest_obstacle_distance=float(np.min(self._lidar)),
            planner_status=self._planner_status,
            recovery_state=self._recovery_state,
            recovery_action=self._recovery_action,
            collision=self._collision,
            timeout=False,
            privileged={
                "human_positions": self._human_positions,
                "nearest_human_distance": nearest_human,
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
        payload = {
            "episode_id": self._metadata.episode_id,
            "outcome": self._outcome.name if self._outcome is not None else "SIMULATOR_FAILURE",
            "outcome_id": int(
                self._outcome if self._outcome is not None else EpisodeOutcome.SIMULATOR_FAILURE
            ),
            "detail": self._outcome_detail,
            "sample_count": self._sample_count,
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
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.finalize()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
