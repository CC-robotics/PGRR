"""ROS-independent construction of deployable recovery observations."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np
import numpy.typing as npt

from ramp_core.observations import (
    RecoveryObservation,
    navigation_path_or_goal,
    select_local_path_waypoints,
)
from ramp_core.types import FailurePrediction, PlannerStatus, Pose2D, Velocity2D


class RecoveryObservationBuilder:
    """Reproduce the node's observation-shaping contract without ROS state.

    This class is intentionally stateless and is not wired into the runtime
    node yet.  Callers must provide only deployable observations; privileged
    simulator state is not accepted.
    """

    @staticmethod
    def build(
        *,
        pose: Pose2D,
        velocity: Velocity2D,
        goal: Pose2D,
        task_path: Iterable[tuple[float, float]],
        lidar_history: Sequence[npt.ArrayLike],
        distance_history: Sequence[float],
        angular_velocity_history: Sequence[float],
        base_action: npt.ArrayLike,
        planner_status: PlannerStatus,
        failure_prediction: FailurePrediction,
    ) -> RecoveryObservation:
        if not lidar_history:
            raise ValueError("lidar history must contain at least one scan")

        distance = math.dist((pose.x, pose.y), (goal.x, goal.y))
        bearing = math.atan2(goal.y - pose.y, goal.x - pose.x) - pose.yaw
        bearing = math.atan2(math.sin(bearing), math.cos(bearing))
        points = navigation_path_or_goal(task_path, (goal.x, goal.y))
        waypoints = select_local_path_waypoints(points, pose)

        lidar = list(lidar_history)
        lidar = [lidar[0]] * (5 - len(lidar)) + lidar
        progress = [float(value) for value in distance_history]
        progress = [distance] * (10 - len(progress)) + progress
        angular = [float(value) for value in angular_velocity_history]
        angular = [0.0] * (10 - len(angular)) + angular

        return RecoveryObservation(
            lidar=np.asarray(lidar[-5:], dtype=np.float32),
            goal_polar=np.asarray([distance, bearing], dtype=np.float32),
            path_waypoints=waypoints,
            robot_velocity=np.asarray([velocity.linear, velocity.angular], dtype=np.float32),
            # RecoveryObservation freezes its arrays. Copy here so a future
            # shadow build cannot make the live controller buffer read-only.
            base_action=np.asarray(base_action, dtype=np.float32).copy(),
            progress_history=np.asarray(progress[-10:], dtype=np.float32),
            angular_velocity_history=np.asarray(angular[-10:], dtype=np.float32),
            planner_status=planner_status,
            failure_prediction=failure_prediction,
        )
