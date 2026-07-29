"""Observable and privileged state containers with leakage-resistant validation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.types import FailurePrediction, PlannerStatus, Pose2D, Velocity2D


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
