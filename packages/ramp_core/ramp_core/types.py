"""Shared strongly typed values and component interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class Pose2D:
    x: float
    y: float
    yaw: float = 0.0


@dataclass(frozen=True, slots=True)
class Velocity2D:
    linear: float
    angular: float


class PlannerStatus(IntEnum):
    UNKNOWN = 0
    ACTIVE = 1
    SUCCEEDED = 2
    NO_VALID_CONTROL = 3
    ABORTED = 4
    CANCELED = 5


def select_planner_status(statuses: Sequence[PlannerStatus]) -> PlannerStatus:
    """Prefer an active goal over stale terminal entries in a status array."""

    if not statuses:
        return PlannerStatus.UNKNOWN
    if PlannerStatus.ACTIVE in statuses:
        return PlannerStatus.ACTIVE
    return statuses[-1]


@dataclass(frozen=True, slots=True)
class FailurePrediction:
    collision_risk: float
    freeze: float
    oscillation: float
    deadlock: float

    def __post_init__(self) -> None:
        for value in self.as_array():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError("failure probabilities must lie in [0, 1]")

    def as_array(self) -> npt.NDArray[np.float32]:
        return np.asarray(
            [self.collision_risk, self.freeze, self.oscillation, self.deadlock],
            dtype=np.float32,
        )

    @property
    def score(self) -> float:
        return max(self.collision_risk, self.freeze, self.oscillation, self.deadlock)


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action_id: int
    confidence: float
    reason: str


class BasePlannerAdapter(Protocol):
    def set_navigation_goal(self, goal: Pose2D) -> None: ...

    def set_recovery_goal(self, goal: Pose2D) -> None: ...

    def cancel(self) -> None: ...

    def get_status(self) -> PlannerStatus: ...

    def get_last_command(self) -> Velocity2D: ...


class FailureDetector(Protocol):
    def predict(self, observation: object) -> FailurePrediction: ...


class RecoveryPolicy(Protocol):
    def select_action(
        self,
        observation: object,
        action_mask: npt.NDArray[np.bool_],
    ) -> RecoveryDecision: ...


class RecoveryExpert(Protocol):
    def label(self, privileged_state: object, candidate_actions: list[object]) -> object: ...
