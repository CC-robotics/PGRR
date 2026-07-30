"""Nav2 NavigateToPose adapter for the selected Arena Humble profile."""

from __future__ import annotations

import math

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from ramp_core.types import PlannerStatus, Pose2D, Velocity2D
from rclpy.action import ActionClient
from rclpy.action.client import ClientGoalHandle
from rclpy.node import Node

from ramp_ros.adapters.base_planner import PlannerAdapter


class Nav2Adapter(PlannerAdapter):
    def __init__(self, node: Node, action_name: str, frame_id: str = "map") -> None:
        self._node = node
        self._frame_id = frame_id
        self._client: ActionClient[
            NavigateToPose.Goal, NavigateToPose.Result, NavigateToPose.Feedback
        ] = ActionClient(node, NavigateToPose, action_name)
        self._status = PlannerStatus.UNKNOWN
        self._goal_handle: (
            ClientGoalHandle[NavigateToPose.Goal, NavigateToPose.Result, NavigateToPose.Feedback]
            | None
        ) = None
        self._last_command = Velocity2D(0.0, 0.0)
        self._original_goal: Pose2D | None = None
        self._submission_serial = 0

    @property
    def ready(self) -> bool:
        return self._client.server_is_ready()

    def remember_navigation_goal(self, goal: Pose2D) -> None:
        """Retain a task-generator goal without submitting a duplicate action."""
        self._original_goal = goal

    def _message(self, goal: Pose2D) -> NavigateToPose.Goal:
        pose = PoseStamped()
        pose.header.frame_id = self._frame_id
        pose.header.stamp = self._node.get_clock().now().to_msg()
        pose.pose.position.x = goal.x
        pose.pose.position.y = goal.y
        pose.pose.orientation.z = math.sin(goal.yaw / 2.0)
        pose.pose.orientation.w = math.cos(goal.yaw / 2.0)
        message = NavigateToPose.Goal()
        message.pose = pose
        return message

    def _submit(self, goal: Pose2D) -> None:
        if not self._client.server_is_ready():
            self._status = PlannerStatus.NO_VALID_CONTROL
            return
        self._submission_serial += 1
        submission_serial = self._submission_serial
        self._status = PlannerStatus.ACTIVE
        future = self._client.send_goal_async(self._message(goal))

        def accepted(done: object) -> None:
            if submission_serial != self._submission_serial:
                return
            goal_handle = done.result()  # type: ignore[attr-defined]
            if not goal_handle.accepted:
                self._status = PlannerStatus.ABORTED
                return
            self._goal_handle = goal_handle
            result_future = goal_handle.get_result_async()

            def finished(result_done: object) -> None:
                if submission_serial != self._submission_serial:
                    return
                status = int(result_done.result().status)  # type: ignore[attr-defined]
                self._status = PlannerStatus.SUCCEEDED if status == 4 else PlannerStatus.ABORTED

            result_future.add_done_callback(finished)

        future.add_done_callback(accepted)

    def set_navigation_goal(self, goal: Pose2D) -> None:
        self._original_goal = goal
        self._submit(goal)

    def set_recovery_goal(self, goal: Pose2D) -> None:
        self._submit(goal)

    def restore_original_goal(self) -> bool:
        if self._original_goal is None:
            return False
        self._submit(self._original_goal)
        return True

    def cancel(self) -> None:
        self._submission_serial += 1
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
        self._status = PlannerStatus.CANCELED

    def update_last_command(self, linear: float, angular: float) -> None:
        self._last_command = Velocity2D(linear, angular)

    def get_status(self) -> PlannerStatus:
        return self._status

    def get_last_command(self) -> Velocity2D:
        return self._last_command
