"""Observable and privileged state containers with leakage-resistant validation."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.types import FailurePrediction, PlannerStatus, Pose2D, Velocity2D


def navigation_path_or_goal(
    path: Iterable[tuple[float, float]],
    goal: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    """Return a non-empty task path, falling back to the original goal."""
    points = tuple((float(x), float(y)) for x, y in path)
    if points:
        return points
    goal_x, goal_y = map(float, goal)
    if not math.isfinite(goal_x) or not math.isfinite(goal_y):
        raise ValueError("goal must contain finite coordinates")
    return ((goal_x, goal_y),)


def _finite_array(
    value: npt.ArrayLike, shape: tuple[int, ...], name: str
) -> npt.NDArray[np.float32]:
    array = np.asarray(value, dtype=np.float32)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or Inf")
    array.setflags(write=False)
    return array


def select_local_path_waypoints(
    path: tuple[tuple[float, float], ...],
    robot_pose: Pose2D,
    *,
    count: int = 8,
) -> npt.NDArray[np.float32]:
    """Select consecutive path points ahead of the robot and express them locally.

    Nav2 plans include the full route from its start. Sampling that full route can
    put already-traversed points into a recovery observation and make a recovery
    policy steer backwards. The closest path point anchors the untraversed suffix;
    its next ``count`` points preserve the local path direction. Short suffixes are
    padded with their final point so the observation shape remains fixed.
    """

    if count <= 0:
        raise ValueError("count must be positive")
    if not path:
        raise ValueError("path must contain at least one point")
    world = np.asarray(path, dtype=np.float64)
    if world.ndim != 2 or world.shape[1] != 2 or not np.all(np.isfinite(world)):
        raise ValueError("path must contain finite (x, y) points")
    robot_xy = np.asarray([robot_pose.x, robot_pose.y], dtype=np.float64)
    closest = int(np.argmin(np.sum((world - robot_xy) ** 2, axis=1)))
    selected = world[closest : closest + count]
    if len(selected) < count:
        selected = np.concatenate(
            [selected, np.repeat(selected[-1][None, :], count - len(selected), axis=0)]
        )
    offsets = selected - robot_xy
    cosine = math.cos(robot_pose.yaw)
    sine = math.sin(robot_pose.yaw)
    local = np.empty((count, 2), dtype=np.float32)
    local[:, 0] = cosine * offsets[:, 0] + sine * offsets[:, 1]
    local[:, 1] = -sine * offsets[:, 0] + cosine * offsets[:, 1]
    return local


@dataclass(frozen=True, slots=True)
class RecoveryObservation:
    lidar: npt.NDArray[np.float32]
    goal_polar: npt.NDArray[np.float32]
    path_waypoints: npt.NDArray[np.float32]
    robot_velocity: npt.NDArray[np.float32]
    base_action: npt.NDArray[np.float32]
    progress_history: npt.NDArray[np.float32]
    angular_velocity_history: npt.NDArray[np.float32]
    planner_status: PlannerStatus
    failure_prediction: FailurePrediction

    def __post_init__(self) -> None:
        object.__setattr__(self, "lidar", _finite_array(self.lidar, (5, 180), "lidar"))
        object.__setattr__(self, "goal_polar", _finite_array(self.goal_polar, (2,), "goal_polar"))
        object.__setattr__(
            self,
            "path_waypoints",
            _finite_array(self.path_waypoints, (8, 2), "path_waypoints"),
        )
        object.__setattr__(
            self,
            "robot_velocity",
            _finite_array(self.robot_velocity, (2,), "robot_velocity"),
        )
        object.__setattr__(
            self, "base_action", _finite_array(self.base_action, (2,), "base_action")
        )
        object.__setattr__(
            self,
            "progress_history",
            _finite_array(self.progress_history, (10,), "progress_history"),
        )
        object.__setattr__(
            self,
            "angular_velocity_history",
            _finite_array(self.angular_velocity_history, (10,), "angular_velocity_history"),
        )
        if np.any(self.lidar < 0.0):
            raise ValueError("lidar ranges must be non-negative")


@dataclass(frozen=True, slots=True)
class HumanState:
    position: tuple[float, float]
    velocity: tuple[float, float]
    radius: float


@dataclass(frozen=True, slots=True)
class PrivilegedState:
    robot_pose: Pose2D
    robot_velocity: Velocity2D
    original_goal: Pose2D
    global_path: tuple[tuple[float, float], ...]
    humans: tuple[HumanState, ...]
    time_step: float
