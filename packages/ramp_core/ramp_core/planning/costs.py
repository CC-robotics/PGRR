"""Cost terms for privileged short-horizon recovery rollouts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExpertCostWeights:
    collision: float = 1_000_000.0
    progress: float = 8.0
    social: float = 4.0
    rejoin: float = 3.0
    length: float = 0.4
    smooth: float = 0.2
    time: float = 0.3
    switch: float = 0.5
    repeat_wait: float = 1.0
    minimum_progress_m: float = 0.20
    personal_space_m: float = 1.0

    def __post_init__(self) -> None:
        if (
            min(
                self.collision,
                self.progress,
                self.social,
                self.rejoin,
                self.length,
                self.smooth,
                self.time,
                self.switch,
                self.repeat_wait,
                self.minimum_progress_m,
                self.personal_space_m,
            )
            < 0.0
        ):
            raise ValueError("expert cost weights and thresholds must be non-negative")


@dataclass(frozen=True, slots=True)
class RolloutCostTerms:
    collision: float
    progress: float
    social: float
    rejoin: float
    length: float
    smooth: float
    time: float
    switch: float
    repeat_wait: float

    def weighted(self, weights: ExpertCostWeights) -> float:
        return (
            weights.collision * self.collision
            + weights.progress * self.progress
            + weights.social * self.social
            + weights.rejoin * self.rejoin
            + weights.length * self.length
            + weights.smooth * self.smooth
            + weights.time * self.time
            + weights.switch * self.switch
            + weights.repeat_wait * self.repeat_wait
        )
