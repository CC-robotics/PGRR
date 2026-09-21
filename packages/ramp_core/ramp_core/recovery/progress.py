"""Observable, runtime-agnostic assessment of one completed recovery cycle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class RecoveryCycleVerdict(str, Enum):
    """Mutually exclusive explanation of a recovery cycle's useful outcome."""

    EFFECTIVE = "EFFECTIVE"
    ORIGINAL_GOAL_NOT_ACTIVE = "ORIGINAL_GOAL_NOT_ACTIVE"
    HAZARD_NOT_CLEARED = "HAZARD_NOT_CLEARED"
    INSUFFICIENT_TASK_PROGRESS = "INSUFFICIENT_TASK_PROGRESS"
    RETRIGGER_OBSERVATION_INCOMPLETE = "RETRIGGER_OBSERVATION_INCOMPLETE"
    RAPID_RETRIGGER = "RAPID_RETRIGGER"


@dataclass(frozen=True, slots=True)
class RecoveryCycleProgressConfig:
    """Explicit development thresholds; no value is silently chosen here."""

    minimum_original_goal_progress_m: float
    minimum_clear_frames: int
    rapid_retrigger_window_s: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum_original_goal_progress_m)
            or self.minimum_original_goal_progress_m <= 0.0
        ):
            raise ValueError("minimum original-goal progress must be finite and positive")
        if self.minimum_clear_frames <= 0:
            raise ValueError("minimum clear-frame count must be positive")
        if (
            not math.isfinite(self.rapid_retrigger_window_s)
            or self.rapid_retrigger_window_s < 0.0
        ):
            raise ValueError("rapid-retrigger window must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class RecoveryCycleEvidence:
    """Observable evidence collected around a single recovery/rejoin cycle."""

    start_original_goal_distance_m: float
    end_original_goal_distance_m: float
    consecutive_clear_frames: int
    original_goal_active: bool
    retrigger_delay_s: float | None
    retrigger_observation_s: float

    def __post_init__(self) -> None:
        distances = (
            self.start_original_goal_distance_m,
            self.end_original_goal_distance_m,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in distances):
            raise ValueError("original-goal distances must be finite and non-negative")
        if self.consecutive_clear_frames < 0:
            raise ValueError("consecutive clear-frame count must be non-negative")
        if self.retrigger_delay_s is not None and (
            not math.isfinite(self.retrigger_delay_s) or self.retrigger_delay_s < 0.0
        ):
            raise ValueError("retrigger delay must be finite and non-negative")
        if not math.isfinite(self.retrigger_observation_s) or self.retrigger_observation_s < 0.0:
            raise ValueError("retrigger observation must be finite and non-negative")
        if (
            self.retrigger_delay_s is not None
            and self.retrigger_delay_s > self.retrigger_observation_s
        ):
            raise ValueError("retrigger delay cannot exceed its observation window")

    @property
    def original_goal_progress_m(self) -> float:
        return self.start_original_goal_distance_m - self.end_original_goal_distance_m


@dataclass(frozen=True, slots=True)
class RecoveryCycleAssessment:
    """Independent checks plus one ordered verdict for reporting and control."""

    verdict: RecoveryCycleVerdict
    original_goal_progress_m: float
    hazard_cleared: bool
    meaningful_task_progress: bool
    rapid_retrigger: bool
    retrigger_observation_complete: bool
    original_goal_active: bool

    @property
    def effective(self) -> bool:
        return self.verdict is RecoveryCycleVerdict.EFFECTIVE


def assess_recovery_cycle(
    evidence: RecoveryCycleEvidence,
    config: RecoveryCycleProgressConfig,
) -> RecoveryCycleAssessment:
    """Assess one cycle without simulator-only or privileged actor fields.

    The ordered verdict reports the earliest unmet contract. Independent flags
    remain available so validation analyses do not lose information.
    """

    progress = evidence.original_goal_progress_m
    hazard_cleared = evidence.consecutive_clear_frames >= config.minimum_clear_frames
    meaningful_progress = progress >= config.minimum_original_goal_progress_m
    rapid_retrigger = (
        evidence.retrigger_delay_s is not None
        and evidence.retrigger_delay_s <= config.rapid_retrigger_window_s
    )
    retrigger_observation_complete = (
        evidence.retrigger_delay_s is not None
        or evidence.retrigger_observation_s >= config.rapid_retrigger_window_s
    )

    if not evidence.original_goal_active:
        verdict = RecoveryCycleVerdict.ORIGINAL_GOAL_NOT_ACTIVE
    elif not hazard_cleared:
        verdict = RecoveryCycleVerdict.HAZARD_NOT_CLEARED
    elif not meaningful_progress:
        verdict = RecoveryCycleVerdict.INSUFFICIENT_TASK_PROGRESS
    elif not retrigger_observation_complete:
        verdict = RecoveryCycleVerdict.RETRIGGER_OBSERVATION_INCOMPLETE
    elif rapid_retrigger:
        verdict = RecoveryCycleVerdict.RAPID_RETRIGGER
    else:
        verdict = RecoveryCycleVerdict.EFFECTIVE

    return RecoveryCycleAssessment(
        verdict=verdict,
        original_goal_progress_m=progress,
        hazard_cleared=hazard_cleared,
        meaningful_task_progress=meaningful_progress,
        rapid_retrigger=rapid_retrigger,
        retrigger_observation_complete=retrigger_observation_complete,
        original_goal_active=evidence.original_goal_active,
    )
