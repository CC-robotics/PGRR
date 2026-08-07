"""ROS2 wrapper for the observable-only rule failure detector."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from ramp_core.failure.labels import FailureType
from ramp_core.failure.rules import RuleFailureConfig, RuleFailureDetector, TimedNavigationSample
from ramp_core.geometry import normalize_angle
from ramp_core.planning.online import sanitize_near_field_returns
from ramp_core.types import PlannerStatus, select_planner_status
from ramp_msgs.msg import FailureStatus, RecoveryDecision
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def _planner_status(status: int) -> PlannerStatus:
    return {
        GoalStatus.STATUS_ACCEPTED: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_EXECUTING: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_SUCCEEDED: PlannerStatus.SUCCEEDED,
        GoalStatus.STATUS_ABORTED: PlannerStatus.ABORTED,
        GoalStatus.STATUS_CANCELED: PlannerStatus.CANCELED,
        GoalStatus.STATUS_CANCELING: PlannerStatus.CANCELED,
    }.get(status, PlannerStatus.UNKNOWN)


def _yaw_from_odometry(message: Odometry) -> float:
    quaternion = message.pose.pose.orientation
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


class FailureDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("failure_detector")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("scan_topic", "scan")
        self.declare_parameter("base_cmd_vel_topic", "cmd_vel")
        self.declare_parameter("nav_status_topic", "navigate_to_pose/_action/status")
        self.declare_parameter("failure_status_topic", "failure_status")
        self.declare_parameter("recovery_decision_topic", "recovery_decision")
        self.declare_parameter("episode_start_topic", "/ramp/episode_started")
        self.declare_parameter("wait_for_episode_start", False)
        self.declare_parameter("goal_x", 0.0)
        self.declare_parameter("goal_y", 0.0)
        self.declare_parameter("goal_tolerance_m", 0.25)
        self.declare_parameter("robot_start_x", 0.0)
        self.declare_parameter("robot_start_y", 0.0)
        self.declare_parameter("robot_start_yaw", 0.0)
        self.declare_parameter("odometry_is_world_frame", False)
        self.declare_parameter("trigger_threshold", 0.65)
        self.declare_parameter("collision_front_sector_degrees", 30.0)
        self.declare_parameter("collision_trend_sector_degrees", 90.0)
        self.declare_parameter("minimum_valid_lidar_range_m", 0.0)
        self.declare_parameter("bilateral_edge_self_return_max_m", 0.34)
        self.declare_parameter("maximum_valid_linear_speed_mps", 2.0)
        self.declare_parameter("maximum_valid_angular_speed_radps", 4.0)
        self.declare_parameter("motion_rule_startup_grace_s", 4.0)
        defaults = RuleFailureConfig()
        for name in defaults.__dataclass_fields__:
            self.declare_parameter(name, getattr(defaults, name))
        config = RuleFailureConfig(
            **{name: self.get_parameter(name).value for name in defaults.__dataclass_fields__}
        )
        self._detector = RuleFailureDetector(config)
        self._goal = (
            float(self.get_parameter("goal_x").value),
            float(self.get_parameter("goal_y").value),
        )
        self._goal_tolerance = float(self.get_parameter("goal_tolerance_m").value)
        self._robot_start = (
            float(self.get_parameter("robot_start_x").value),
            float(self.get_parameter("robot_start_y").value),
            float(self.get_parameter("robot_start_yaw").value),
        )
        self._trigger_threshold = float(self.get_parameter("trigger_threshold").value)
        if not 0.0 <= self._trigger_threshold <= 1.0:
            raise ValueError("trigger_threshold must lie in [0, 1]")
        self._scan_minimum: float | None = None
        self._scan_minimum_bearing: float | None = None
        self._front_scan_minimum: float | None = None
        self._collision_scan_minimum: float | None = None
        self._collision_scan_minimum_bearing: float | None = None
        self._base_command = (0.0, 0.0)
        self._planner_status = PlannerStatus.UNKNOWN
        self._last_timestamp: float | None = None
        self._motion_rules_enabled = True
        self._episode_started = not bool(self.get_parameter("wait_for_episode_start").value)
        self._episode_started_at_s: float | None = None
        self._publisher = self.create_publisher(
            FailureStatus, str(self.get_parameter("failure_status_topic").value), 10
        )
        self._subscription_handles: list[Any] = [
            self.create_subscription(
                LaserScan,
                str(self.get_parameter("scan_topic").value),
                self._on_scan,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                Twist,
                str(self.get_parameter("base_cmd_vel_topic").value),
                self._on_base_command,
                10,
            ),
            self.create_subscription(
                GoalStatusArray,
                str(self.get_parameter("nav_status_topic").value),
                self._on_status,
                10,
            ),
            self.create_subscription(
                Odometry,
                str(self.get_parameter("odom_topic").value),
                self._on_odom,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                RecoveryDecision,
                str(self.get_parameter("recovery_decision_topic").value),
                self._on_recovery_decision,
                10,
            ),
            self.create_subscription(
                Bool,
                str(self.get_parameter("episode_start_topic").value),
                self._on_episode_start,
                10,
            ),
        ]

    def _on_episode_start(self, message: Bool) -> None:
        if not bool(message.data) or self._episode_started:
            return
        # Gazebo publishes scans while Nav2 and the episode logger are still
        # starting. Spawn/reset motion in that interval can create a latched
        # closing trend that is unrelated to the evaluated episode. Start the
        # detector history at the same explicit handshake used by actors,
        # command mux, and the logger.
        self._detector.reset()
        self._last_timestamp = None
        self._episode_started_at_s = None
        self._episode_started = True

    def _on_scan(self, message: LaserScan) -> None:
        ranges = sanitize_near_field_returns(
            message.ranges,
            minimum_valid_range_m=float(self.get_parameter("minimum_valid_lidar_range_m").value),
            bilateral_edge_self_return_max_m=float(
                self.get_parameter("bilateral_edge_self_return_max_m").value
            ),
        )
        angles = float(message.angle_min) + np.arange(ranges.size) * float(message.angle_increment)
        half_width = math.radians(
            float(self.get_parameter("collision_front_sector_degrees").value) / 2.0
        )
        trend_half_width = math.radians(
            float(self.get_parameter("collision_trend_sector_degrees").value) / 2.0
        )
        front = np.abs(np.arctan2(np.sin(angles), np.cos(angles))) <= half_width
        collision_sector = np.abs(np.arctan2(np.sin(angles), np.cos(angles))) <= trend_half_width
        valid = np.isfinite(ranges) & (ranges >= 0.0)
        valid_indices = np.flatnonzero(valid)
        front_indices = np.flatnonzero(front & valid)
        collision_indices = np.flatnonzero(collision_sector & valid)
        if valid_indices.size and front_indices.size and collision_indices.size:
            nearest_index = int(valid_indices[int(np.argmin(ranges[valid_indices]))])
            front_index = int(front_indices[int(np.argmin(ranges[front_indices]))])
            collision_index = int(collision_indices[int(np.argmin(ranges[collision_indices]))])
            self._scan_minimum = float(ranges[nearest_index])
            self._scan_minimum_bearing = float(angles[nearest_index])
            self._front_scan_minimum = float(ranges[front_index])
            self._collision_scan_minimum = float(ranges[collision_index])
            self._collision_scan_minimum_bearing = float(angles[collision_index])

    def _on_base_command(self, message: Twist) -> None:
        self._base_command = float(message.linear.x), float(message.angular.z)

    def _on_status(self, message: GoalStatusArray) -> None:
        if message.status_list:
            self._planner_status = select_planner_status(
                [_planner_status(int(item.status)) for item in message.status_list]
            )

    def _on_recovery_decision(self, message: RecoveryDecision) -> None:
        # Continue accumulating stopped-motion evidence while the independent
        # safety layer owns the command. Otherwise a persistent emergency stop
        # clears the detector history forever and the learned recovery policy
        # can never receive the resulting freeze/deadlock state after release.
        self._motion_rules_enabled = int(message.recovery_state) in {
            RecoveryDecision.NORMAL,
            RecoveryDecision.PENDING_RECOVERY,
            RecoveryDecision.EMERGENCY_STOP,
        }

    def _on_odom(self, message: Odometry) -> None:
        if not self._episode_started:
            return
        if (
            self._scan_minimum is None
            or self._scan_minimum_bearing is None
            or self._front_scan_minimum is None
            or self._collision_scan_minimum is None
            or self._collision_scan_minimum_bearing is None
        ):
            return
        stamp = message.header.stamp
        timestamp = float(stamp.sec) + float(stamp.nanosec) * 1.0e-9
        # DDS may deliver a stale odometry sample after a newer sample when
        # Nav2 goals are preempted. Resetting temporal rules here creates a
        # collision-warning blind spot. Each episode launches a fresh node,
        # so non-increasing samples are safely discarded instead.
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            return
        linear_velocity = float(message.twist.twist.linear.x)
        angular_velocity = float(message.twist.twist.angular.z)
        # Gazebo's pose-derived odometry differentiates across the initial
        # spawn/reset jump. The first post-handshake sample can consequently
        # report tens of metres per second while the command mux is holding
        # zero. Feeding that impossible value into braking distance creates a
        # two-second false collision latch at every episode start.
        if abs(linear_velocity) > float(
            self.get_parameter("maximum_valid_linear_speed_mps").value
        ) or abs(angular_velocity) > float(
            self.get_parameter("maximum_valid_angular_speed_radps").value
        ):
            return
        self._last_timestamp = timestamp
        if self._episode_started_at_s is None:
            self._episode_started_at_s = timestamp
        local_x = float(message.pose.pose.position.x)
        local_y = float(message.pose.pose.position.y)
        start_x, start_y, start_yaw = self._robot_start
        local_yaw = _yaw_from_odometry(message)
        if bool(self.get_parameter("odometry_is_world_frame").value):
            world_x, world_y = local_x, local_y
            world_yaw = local_yaw
        else:
            world_x = start_x + math.cos(start_yaw) * local_x - math.sin(start_yaw) * local_y
            world_y = start_y + math.sin(start_yaw) * local_x + math.cos(start_yaw) * local_y
            world_yaw = normalize_angle(start_yaw + local_yaw)
        goal_distance = math.dist((world_x, world_y), self._goal)
        prediction = self._detector.update(
            TimedNavigationSample(
                timestamp=timestamp,
                position=(world_x, world_y),
                goal_distance=goal_distance,
                linear_velocity=linear_velocity,
                angular_velocity=angular_velocity,
                base_linear_command=self._base_command[0],
                base_angular_command=self._base_command[1],
                nearest_lidar_distance=self._scan_minimum,
                forward_lidar_distance=self._front_scan_minimum,
                collision_lidar_distance=self._collision_scan_minimum,
                nearest_lidar_bearing=normalize_angle(world_yaw + self._scan_minimum_bearing),
                collision_lidar_bearing=normalize_angle(
                    world_yaw + self._collision_scan_minimum_bearing
                ),
                planner_status=self._planner_status,
                goal_reached=goal_distance <= self._goal_tolerance,
            ),
            motion_rules_enabled=(
                self._motion_rules_enabled
                and timestamp - self._episode_started_at_s
                >= float(self.get_parameter("motion_rule_startup_grace_s").value)
            ),
        )
        probabilities = prediction.as_array()
        output = FailureStatus()
        output.stamp = message.header.stamp
        output.collision_risk = float(prediction.collision_risk)
        output.freeze = float(prediction.freeze)
        output.oscillation = float(prediction.oscillation)
        output.deadlock = float(prediction.deadlock)
        output.failure_score = float(prediction.score)
        output.dominant_type = int(FailureType(int(np.argmax(probabilities))))
        output.triggered = prediction.score >= self._trigger_threshold
        self._publisher.publish(output)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: FailureDetectorNode | None = None
    try:
        node = FailureDetectorNode()
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
