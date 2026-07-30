#!/usr/bin/env python3
"""Verify that direct recovery commands exclusively override classical commands."""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import Twist
from ramp_core.action_space import BACKUP_ACTION_ID, WAIT_ACTION_ID
from ramp_msgs.msg import RecoveryDecision
from ramp_ros.nodes.goal_mux_node import GoalMuxNode
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node


class MuxDriver(Node):
    def __init__(self) -> None:
        super().__init__("goal_mux_smoke_driver")
        self.base_publisher = self.create_publisher(Twist, "/base_cmd_vel", 10)
        self.recovery_publisher = self.create_publisher(Twist, "/recovery_cmd_vel", 10)
        self.decision_publisher = self.create_publisher(RecoveryDecision, "/recovery_decision", 10)
        self.outputs: list[Twist] = []
        self.subscription = self.create_subscription(Twist, "/cmd_vel", self.outputs.append, 10)

    def publish(self, state: int, action: int, recovery_speed: float) -> None:
        base = Twist()
        base.linear.x = 0.30
        recovery = Twist()
        recovery.linear.x = recovery_speed
        decision = RecoveryDecision()
        decision.recovery_state = state
        decision.action_id = action
        self.base_publisher.publish(base)
        self.recovery_publisher.publish(recovery)
        self.decision_publisher.publish(decision)


def _wait_for_speed(
    executor: SingleThreadedExecutor,
    driver: MuxDriver,
    expected: float,
    *,
    state: int,
    action: int,
    recovery_speed: float,
) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        driver.publish(state, action, recovery_speed)
        for _ in range(4):
            executor.spin_once(timeout_sec=0.03)
        if driver.outputs and abs(driver.outputs[-1].linear.x - expected) < 1.0e-6:
            return
    observed = driver.outputs[-1].linear.x if driver.outputs else None
    raise RuntimeError(f"expected mux speed {expected}, observed {observed}")


def main() -> int:
    rclpy.init()
    mux = GoalMuxNode()
    driver = MuxDriver()
    executor = SingleThreadedExecutor()
    executor.add_node(mux)
    executor.add_node(driver)
    try:
        _wait_for_speed(
            executor,
            driver,
            0.30,
            state=RecoveryDecision.NORMAL,
            action=-1,
            recovery_speed=0.0,
        )
        _wait_for_speed(
            executor,
            driver,
            0.0,
            state=RecoveryDecision.PENDING_RECOVERY,
            action=-1,
            recovery_speed=0.0,
        )
        _wait_for_speed(
            executor,
            driver,
            0.0,
            state=RecoveryDecision.RECOVERY,
            action=WAIT_ACTION_ID,
            recovery_speed=0.0,
        )
        _wait_for_speed(
            executor,
            driver,
            -0.15,
            state=RecoveryDecision.RECOVERY,
            action=BACKUP_ACTION_ID,
            recovery_speed=-0.15,
        )
        _wait_for_speed(
            executor,
            driver,
            0.30,
            state=RecoveryDecision.RECOVERY,
            action=0,
            recovery_speed=-0.15,
        )
        _wait_for_speed(
            executor,
            driver,
            0.0,
            state=RecoveryDecision.SUCCEEDED,
            action=0,
            recovery_speed=-0.15,
        )
        print(
            "PASS goal mux ROS smoke: "
            "normal=0.30 pending=0.00 wait=0.00 backup=-0.15 "
            "subgoal=0.30 succeeded=0.00"
        )
        return 0
    finally:
        executor.remove_node(driver)
        executor.remove_node(mux)
        driver.destroy_node()
        mux.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
