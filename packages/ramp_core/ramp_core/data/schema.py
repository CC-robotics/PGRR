"""Typed raw-navigation records with explicit observable/privileged separation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any

import numpy as np
import numpy.typing as npt


class EpisodeOutcome(IntEnum):
    GOAL_REACHED = 0
    COLLISION = 1
    TIMEOUT = 2
    PLANNER_FAILURE = 3
    SIMULATOR_FAILURE = 4
    INVALID_RESET = 5


@dataclass(frozen=True, slots=True)
class EpisodeMetadata:
    episode_id: str
    scenario_id: str
    map_id: str
    seed: int
    split: str
    planner_id: str
    source_policy: str
    arena_commit: str
    project_commit: str
    timestamp: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        required = (
            self.episode_id,
            self.scenario_id,
            self.map_id,
            self.split,
            self.planner_id,
            self.source_policy,
            self.arena_commit,
            self.project_commit,
            self.timestamp,
        )
        if any(not value.strip() for value in required):
            raise ValueError("metadata string fields must be non-empty")
        if self.schema_version != 1:
            raise ValueError("unsupported episode schema version")


def _vector(value: npt.ArrayLike, size: int, name: str) -> npt.NDArray[np.float32]:
    result = np.asarray(value, dtype=np.float32)
    if result.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},), got {result.shape}")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} contains NaN or Inf")
    result.setflags(write=False)
    return result


@dataclass(frozen=True, slots=True)
class NavigationStep:
    timestamp: float
    robot_pose: npt.NDArray[np.float32]
    robot_velocity: npt.NDArray[np.float32]
    cmd_vel: npt.NDArray[np.float32]
    base_cmd_vel: npt.NDArray[np.float32]
    goal: npt.NDArray[np.float32]
    distance_to_goal: float
    global_path: tuple[tuple[float, float], ...]
    lidar: npt.NDArray[np.float32]
    nearest_obstacle_distance: float
    planner_status: int
    failure_prediction: npt.NDArray[np.float32]
    failure_score: float
    recovery_state: int
    recovery_action: int
    collision: bool
    timeout: bool
    recovery_reason: str = ""
    privileged: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not np.isfinite(self.timestamp) or self.timestamp < 0.0:
            raise ValueError("timestamp must be finite and non-negative")
        object.__setattr__(self, "robot_pose", _vector(self.robot_pose, 3, "robot_pose"))
        object.__setattr__(
            self, "robot_velocity", _vector(self.robot_velocity, 2, "robot_velocity")
        )
        object.__setattr__(self, "cmd_vel", _vector(self.cmd_vel, 2, "cmd_vel"))
        object.__setattr__(self, "base_cmd_vel", _vector(self.base_cmd_vel, 2, "base_cmd_vel"))
        object.__setattr__(self, "goal", _vector(self.goal, 3, "goal"))
        object.__setattr__(self, "lidar", _vector(self.lidar, 180, "lidar"))
        object.__setattr__(
            self,
            "failure_prediction",
            _vector(self.failure_prediction, 4, "failure_prediction"),
        )
        if not np.isfinite(self.distance_to_goal) or self.distance_to_goal < 0.0:
            raise ValueError("distance_to_goal must be finite and non-negative")
        if not np.isfinite(self.nearest_obstacle_distance) or self.nearest_obstacle_distance < 0.0:
            raise ValueError("nearest_obstacle_distance must be finite and non-negative")
        if not np.isfinite(self.failure_score) or not 0.0 <= self.failure_score <= 1.0:
            raise ValueError("failure_score must be finite and lie in [0, 1]")
        if np.any(self.failure_prediction < 0.0) or np.any(self.failure_prediction > 1.0):
            raise ValueError("failure_prediction values must lie in [0, 1]")
        if np.any(self.lidar < 0.0):
            raise ValueError("lidar ranges must be non-negative")
        if not isinstance(self.recovery_reason, str):
            raise TypeError("recovery_reason must be a string")
        path = np.asarray(self.global_path, dtype=np.float32)
        if path.size == 0:
            return
        if path.ndim != 2 or path.shape[1:] != (2,) or not np.all(np.isfinite(path)):
            raise ValueError("global_path must be a finite sequence of (x, y) points")

    def as_jsonable(self) -> dict[str, Any]:
        record = asdict(self)
        for name in (
            "robot_pose",
            "robot_velocity",
            "cmd_vel",
            "base_cmd_vel",
            "goal",
            "lidar",
            "failure_prediction",
        ):
            record[name] = getattr(self, name).tolist()
        record["global_path"] = [list(point) for point in self.global_path]
        return record
