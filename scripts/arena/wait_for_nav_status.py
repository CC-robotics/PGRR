#!/usr/bin/env python3
"""Wait for a task-generated Nav2 goal to reach a terminal status."""

from __future__ import annotations

import argparse
import time

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from rclpy.node import Node


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--timeout", type=float, default=150.0)
    arguments, ros_arguments = parser.parse_known_args()
    rclpy.init(args=ros_arguments)
    node = Node("ramp_navigation_status_monitor")
    active_goal_ids: set[tuple[int, ...]] = set()
    succeeded = False

    def callback(message: GoalStatusArray) -> None:
        nonlocal succeeded
        for entry in message.status_list:
            goal_id = tuple(entry.goal_info.goal_id.uuid)
            if entry.status in (GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING):
                active_goal_ids.add(goal_id)
            if entry.status == GoalStatus.STATUS_SUCCEEDED and (
                goal_id in active_goal_ids or not active_goal_ids
            ):
                print(f"GOAL_REACHED goal_id={bytes(goal_id).hex()}", flush=True)
                succeeded = True

    node.create_subscription(GoalStatusArray, arguments.topic, callback, 10)
    deadline = time.monotonic() + arguments.timeout
    while not succeeded and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
    node.destroy_node()
    rclpy.try_shutdown()
    if not succeeded:
        raise SystemExit("navigation status monitor timed out without STATUS_SUCCEEDED")


if __name__ == "__main__":
    main()
