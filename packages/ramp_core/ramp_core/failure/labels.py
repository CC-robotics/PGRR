"""Canonical failure classes and dense temporal label containers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from ramp_core.failure.rules import RuleFailureConfig, TimedNavigationSample


class FailureType(IntEnum):
    COLLISION_RISK = 0
    FREEZE = 1
    OSCILLATION = 2
    DEADLOCK = 3


@dataclass(frozen=True, slots=True)
class FailureLabelSeries:
    failure: npt.NDArray[np.bool_]
    failure_any: npt.NDArray[np.bool_]
    time_to_failure: npt.NDArray[np.float32]
    failure_onset: npt.NDArray[np.bool_]
    failure_end: npt.NDArray[np.bool_]

    def __post_init__(self) -> None:
        failure = np.asarray(self.failure, dtype=np.bool_)
        if failure.ndim != 2 or failure.shape[1] != len(FailureType):
            raise ValueError("failure must have shape [T, 4]")
        length = failure.shape[0]
        arrays = {
            "failure_any": np.asarray(self.failure_any, dtype=np.bool_),
            "time_to_failure": np.asarray(self.time_to_failure, dtype=np.float32),
            "failure_onset": np.asarray(self.failure_onset, dtype=np.bool_),
            "failure_end": np.asarray(self.failure_end, dtype=np.bool_),
        }
        for name, array in arrays.items():
            if array.shape != (length,):
                raise ValueError(f"{name} must have shape [T]")
        if not np.all(np.isfinite(arrays["time_to_failure"]) | np.isinf(arrays["time_to_failure"])):
            raise ValueError("time_to_failure contains NaN")
        object.__setattr__(self, "failure", failure)
        for name, array in arrays.items():
            object.__setattr__(self, name, array)


def generate_failure_labels(
    samples: Sequence[TimedNavigationSample],
    *,
    config: RuleFailureConfig,
    collision_times: Sequence[float] = (),
    collision_lookahead_s: float = 2.0,
    pre_failure_window_s: float = 3.0,
    post_failure_window_s: float = 1.0,
) -> FailureLabelSeries:
    """Generate dense labels; privileged collision times affect collision labels only."""
    from ramp_core.failure.rules import RuleFailureDetector

    if not samples:
        raise ValueError("at least one navigation sample is required")
    if min(collision_lookahead_s, pre_failure_window_s, post_failure_window_s) < 0.0:
        raise ValueError("label windows must be non-negative")
    timestamps = np.asarray([sample.timestamp for sample in samples], dtype=np.float64)
    if np.any(np.diff(timestamps) < 0.0):
        raise ValueError("sample timestamps must be monotonic")

    detector = RuleFailureDetector(config)
    raw = np.asarray(
        [detector.update(sample).as_array() >= 0.5 for sample in samples], dtype=np.bool_
    )
    for collision_time in collision_times:
        if not np.isfinite(collision_time):
            raise ValueError("collision times must be finite")
        raw[:, FailureType.COLLISION_RISK] |= (
            timestamps >= collision_time - collision_lookahead_s
        ) & (timestamps <= collision_time)

    expanded = np.zeros_like(raw)
    for failure_type in FailureType:
        for index in np.flatnonzero(raw[:, failure_type]):
            left = int(
                np.searchsorted(timestamps, timestamps[index] - pre_failure_window_s, side="left")
            )
            right = int(
                np.searchsorted(timestamps, timestamps[index] + post_failure_window_s, side="right")
            )
            expanded[left:right, failure_type] = True

    failure_any = np.any(expanded, axis=1)
    previous = np.concatenate((np.asarray([False]), failure_any[:-1]))
    following = np.concatenate((failure_any[1:], np.asarray([failure_any[-1]])))
    onset = failure_any & ~previous
    end = failure_any & ~following
    time_to_failure = np.full(len(samples), np.inf, dtype=np.float32)
    next_onset = math.inf
    for index in range(len(samples) - 1, -1, -1):
        if onset[index]:
            next_onset = float(timestamps[index])
        if math.isfinite(next_onset):
            time_to_failure[index] = max(0.0, next_onset - float(timestamps[index]))
    return FailureLabelSeries(expanded, failure_any, time_to_failure, onset, end)
