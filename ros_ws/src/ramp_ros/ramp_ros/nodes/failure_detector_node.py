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
from ramp_core.types import PlannerStatus
from ramp_msgs.msg import FailureStatus
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def _planner_status(status: int) -> PlannerStatus:
    return {
        GoalStatus.STATUS_ACCEPTED: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_EXECUTING: PlannerStatus.ACTIVE,
        GoalStatus.STATUS_SUCCEEDED: PlannerStatus.SUCCEEDED,
        GoalStatus.STATUS_ABORTED: PlannerStatus.ABORTED,
        GoalStatus.STATUS_CANCELED: PlannerStatus.CANCELED,
        GoalStatus.STATUS_CANCELING: PlannerStatus.CANCELED,
    }.get(status, PlannerStatus.UNKNOWN)


class FailureDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("failure_detector")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("scan_topic", "scan")
        self.declare_parameter("base_cmd_vel_topic", "cmd_vel")
        self.declare_parameter("nav_status_topic", "navigate_to_pose/_action/status")
        self.declare_parameter("failure_status_topic", "failure_status")
        self.declare_parameter("goal_x", 0.0)
        self.declare_parameter("goal_y", 0.0)
        self.declare_parameter("goal_tolerance_m", 0.25)
        self.declare_parameter("robot_start_x", 0.0)
        self.declare_parameter("robot_start_y", 0.0)
        self.declare_parameter("robot_start_yaw", 0.0)
        self.declare_parameter("trigger_threshold", 0.65)
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
        self._base_command = (0.0, 0.0)
        self._planner_status = PlannerStatus.UNKNOWN
        self._last_timestamp: float | None = None
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
        ]

    def _on_scan(self, message: LaserScan) -> None:
        ranges = np.asarray(message.ranges, dtype=np.float64)
        finite = ranges[np.isfinite(ranges) & (ranges >= 0.0)]
        if finite.size:
            self._scan_minimum = float(np.min(finite))

    def _on_base_command(self, message: Twist) -> None:
        self._base_command = float(message.linear.x), float(message.angular.z)

    def _on_status(self, message: GoalStatusArray) -> None:
        if message.status_list:
            self._planner_status = _planner_status(int(message.status_list[-1].status))

    def _on_odom(self, message: Odometry) -> None:
        if self._scan_minimum is None:
            return
        stamp = message.header.stamp
        timestamp = float(stamp.sec) + float(stamp.nanosec) * 1.0e-9
        if self._last_timestamp is not None:
            if timestamp < self._last_timestamp:
                self._detector.reset()
            elif timestamp == self._last_timestamp:
                return
        self._last_timestamp = timestamp
        local_x = float(message.pose.pose.position.x)
        local_y = float(message.pose.pose.position.y)
        start_x, start_y, start_yaw = self._robot_start
        world_x = start_x + math.cos(start_yaw) * local_x - math.sin(start_yaw) * local_y
        world_y = start_y + math.sin(start_yaw) * local_x + math.cos(start_yaw) * local_y
        goal_distance = math.dist((world_x, world_y), self._goal)
        prediction = self._detector.update(
            TimedNavigationSample(
                timestamp=timestamp,
                position=(world_x, world_y),
                goal_distance=goal_distance,
                linear_velocity=float(message.twist.twist.linear.x),
                angular_velocity=float(message.twist.twist.angular.z),
                base_linear_command=self._base_command[0],
                base_angular_command=self._base_command[1],
                nearest_lidar_distance=self._scan_minimum,
                planner_status=self._planner_status,
                goal_reached=goal_distance <= self._goal_tolerance,
            )
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
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
