"""Single-writer velocity mux for classical planning and direct recovery behaviors."""

from __future__ import annotations

from typing import Any

import rclpy
from geometry_msgs.msg import Twist
from ramp_core.action_space import BACKUP_ACTION_ID, WAIT_ACTION_ID
from ramp_msgs.msg import RecoveryDecision
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class GoalMuxNode(Node):
    def __init__(self) -> None:
        super().__init__("goal_mux")
        self.declare_parameter("base_cmd_vel_topic", "base_cmd_vel")
        self.declare_parameter("recovery_cmd_vel_topic", "recovery_cmd_vel")
        self.declare_parameter("cmd_vel_topic", "cmd_vel")
        self.declare_parameter("recovery_decision_topic", "recovery_decision")
        self.declare_parameter("publish_frequency_hz", 20.0)
        self.declare_parameter("command_timeout_s", 0.5)
        frequency = float(self.get_parameter("publish_frequency_hz").value)
        if frequency <= 0.0:
            raise ValueError("publish_frequency_hz must be positive")
        self._timeout = float(self.get_parameter("command_timeout_s").value)
        if self._timeout <= 0.0:
            raise ValueError("command_timeout_s must be positive")
        self._base = Twist()
        self._recovery = Twist()
        self._base_stamp = float("-inf")
        self._recovery_stamp = float("-inf")
        self._recovery_state = RecoveryDecision.NORMAL
        self._recovery_action = -1
        self._publisher = self.create_publisher(
            Twist, str(self.get_parameter("cmd_vel_topic").value), 10
        )
        self._subscription_handles: list[Any] = [
            self.create_subscription(
                Twist,
                str(self.get_parameter("base_cmd_vel_topic").value),
                self._on_base,
                10,
            ),
            self.create_subscription(
                Twist,
                str(self.get_parameter("recovery_cmd_vel_topic").value),
                self._on_recovery,
                10,
            ),
            self.create_subscription(
                RecoveryDecision,
                str(self.get_parameter("recovery_decision_topic").value),
                self._on_decision,
                10,
            ),
        ]
        self._timer = self.create_timer(1.0 / frequency, self._publish)

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds * 1.0e-9

    def _on_base(self, message: Twist) -> None:
        self._base = message
        self._base_stamp = self._now()

    def _on_recovery(self, message: Twist) -> None:
        self._recovery = message
        self._recovery_stamp = self._now()

    def _on_decision(self, message: RecoveryDecision) -> None:
        self._recovery_state = int(message.recovery_state)
        self._recovery_action = int(message.action_id)

    def _publish(self) -> None:
        now = self._now()
        terminal_stop = self._recovery_state in {
            RecoveryDecision.FAILED,
            RecoveryDecision.SUCCEEDED,
        }
        direct_recovery = self._recovery_state == RecoveryDecision.EMERGENCY_STOP or (
            self._recovery_state == RecoveryDecision.RECOVERY
            and self._recovery_action in {WAIT_ACTION_ID, BACKUP_ACTION_ID}
        )
        if terminal_stop:
            output = Twist()
        elif direct_recovery:
            output = self._recovery if now - self._recovery_stamp <= self._timeout else Twist()
        else:
            output = self._base if now - self._base_stamp <= self._timeout else Twist()
        self._publisher.publish(output)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: GoalMuxNode | None = None
    try:
        node = GoalMuxNode()
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
