#!/usr/bin/env python3
"""Exercise the rule detector node through real ROS2 messages."""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from ramp_msgs.msg import FailureStatus
from ramp_ros.nodes.failure_detector_node import FailureDetectorNode
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class DetectorDriver(Node):
    def __init__(self) -> None:
        super().__init__("failure_detector_smoke_driver")
        self.scan_publisher = self.create_publisher(LaserScan, "/scan", qos_profile_sensor_data)
        self.odom_publisher = self.create_publisher(Odometry, "/odom", qos_profile_sensor_data)
        self.command_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.received: list[FailureStatus] = []
        self.subscription = self.create_subscription(
            FailureStatus, "/failure_status", self.received.append, 10
        )

    def publish_imminent_collision(self, sample_index: int) -> None:
        scan = LaserScan()
        scan.header.stamp.sec = sample_index
        scan.range_min = 0.05
        scan.range_max = 10.0
        scan.ranges = [0.20] * 180
        command = Twist()
        command.linear.x = 1.0
        odometry = Odometry()
        odometry.header.stamp.sec = sample_index
        odometry.twist.twist.linear.x = 1.0
        self.scan_publisher.publish(scan)
        self.command_publisher.publish(command)
        self.odom_publisher.publish(odometry)


def main() -> int:
    rclpy.init()
    detector = FailureDetectorNode()
    driver = DetectorDriver()
    executor = SingleThreadedExecutor()
    executor.add_node(detector)
    executor.add_node(driver)
    try:
        deadline = time.monotonic() + 8.0
        sample_index = 1
        while time.monotonic() < deadline and not driver.received:
            driver.publish_imminent_collision(sample_index)
            sample_index += 1
            executor.spin_once(timeout_sec=0.1)
            executor.spin_once(timeout_sec=0.1)
        if not driver.received:
            raise RuntimeError("failure detector published no status within 8 seconds")
        output = driver.received[-1]
        if output.collision_risk < 0.99 or not output.triggered:
            raise RuntimeError(
                "imminent collision was not triggered: "
                f"collision_risk={output.collision_risk}, triggered={output.triggered}"
            )
        print(
            "PASS failure detector ROS smoke: "
            f"collision_risk={output.collision_risk:.3f}, "
            f"failure_score={output.failure_score:.3f}"
        )
        return 0
    finally:
        executor.remove_node(driver)
        executor.remove_node(detector)
        driver.destroy_node()
        detector.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
