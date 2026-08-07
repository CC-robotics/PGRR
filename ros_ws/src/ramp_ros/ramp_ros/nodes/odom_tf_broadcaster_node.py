from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster


class OdometryTransformBroadcaster(Node):
    """Broadcast the pose carried by Gazebo ground-truth odometry as TF."""

    def __init__(self) -> None:
        super().__init__("odom_tf_broadcaster")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("parent_frame", "")
        self.declare_parameter("child_frame", "")
        self._broadcaster = TransformBroadcaster(self)
        self._published_first_transform = False
        self._subscription = self.create_subscription(
            Odometry,
            str(self.get_parameter("odom_topic").value),
            self._on_odometry,
            qos_profile_sensor_data,
        )

    @staticmethod
    def _frame(value: str) -> str:
        return value.strip().lstrip("/")

    def _on_odometry(self, message: Odometry) -> None:
        parent_override = self._frame(str(self.get_parameter("parent_frame").value))
        child_override = self._frame(str(self.get_parameter("child_frame").value))
        parent = parent_override or self._frame(message.header.frame_id)
        child = child_override or self._frame(message.child_frame_id)
        pose = message.pose.pose
        values = (
            pose.position.x,
            pose.position.y,
            pose.position.z,
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        )
        if not parent or not child or parent == child:
            self.get_logger().error(
                f"invalid odometry TF frames parent={parent!r} child={child!r}",
                throttle_duration_sec=5.0,
            )
            return
        if not all(math.isfinite(float(value)) for value in values):
            self.get_logger().error(
                "odometry contains a non-finite pose; TF was not published",
                throttle_duration_sec=5.0,
            )
            return
        quaternion_norm = math.sqrt(
            float(pose.orientation.x) ** 2
            + float(pose.orientation.y) ** 2
            + float(pose.orientation.z) ** 2
            + float(pose.orientation.w) ** 2
        )
        if quaternion_norm < 1.0e-9:
            self.get_logger().error(
                "odometry contains a zero-norm quaternion; TF was not published",
                throttle_duration_sec=5.0,
            )
            return

        transform = TransformStamped()
        transform.header = message.header
        transform.header.frame_id = parent
        transform.child_frame_id = child
        transform.transform.translation.x = float(pose.position.x)
        transform.transform.translation.y = float(pose.position.y)
        transform.transform.translation.z = float(pose.position.z)
        transform.transform.rotation.x = float(pose.orientation.x) / quaternion_norm
        transform.transform.rotation.y = float(pose.orientation.y) / quaternion_norm
        transform.transform.rotation.z = float(pose.orientation.z) / quaternion_norm
        transform.transform.rotation.w = float(pose.orientation.w) / quaternion_norm
        self._broadcaster.sendTransform(transform)
        if not self._published_first_transform:
            self._published_first_transform = True
            self.get_logger().info(f"broadcast first odometry transform {parent} -> {child}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: OdometryTransformBroadcaster | None = None
    try:
        node = OdometryTransformBroadcaster()
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
