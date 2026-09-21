"""Default-off shadow comparison for recovery observations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

import numpy as np

from ramp_core.observations import RecoveryObservation

ARRAY_FIELDS = (
    "lidar",
    "goal_polar",
    "path_waypoints",
    "robot_velocity",
    "base_action",
    "progress_history",
    "angular_velocity_history",
)


@dataclass(frozen=True, slots=True)
class ObservationShadowResult:
    """One non-authoritative comparison between live and candidate observations."""

    equivalent: bool
    field_max_abs_error: dict[str, float | None]
    shape_equal: dict[str, bool]
    metadata_equal: bool
    absolute_tolerance: float
    candidate_error_type: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "equivalent": self.equivalent,
            "field_max_abs_error": self.field_max_abs_error,
            "shape_equal": self.shape_equal,
            "metadata_equal": self.metadata_equal,
            "absolute_tolerance": self.absolute_tolerance,
            "candidate_error_type": self.candidate_error_type,
            "authoritative_path_changed": False,
        }


class ObservationShadowComparator:
    """Compare a candidate lazily while leaving the reference path authoritative.

    The comparator is disabled by default. When disabled, the candidate factory
    is never evaluated, which prevents hidden work or exceptions from changing
    the current runtime path.
    """

    def __init__(self, *, enabled: bool = False, absolute_tolerance: float = 0.0) -> None:
        if not np.isfinite(absolute_tolerance) or absolute_tolerance < 0.0:
            raise ValueError("absolute tolerance must be finite and non-negative")
        self.enabled = bool(enabled)
        self.absolute_tolerance = float(absolute_tolerance)

    def compare(
        self,
        reference: RecoveryObservation,
        candidate_factory: Callable[[], RecoveryObservation],
    ) -> ObservationShadowResult | None:
        if not self.enabled:
            return None

        try:
            candidate = candidate_factory()
            errors: dict[str, float | None] = {}
            shapes: dict[str, bool] = {}
            for field in ARRAY_FIELDS:
                reference_value = getattr(reference, field)
                candidate_value = getattr(candidate, field)
                same_shape = reference_value.shape == candidate_value.shape
                shapes[field] = same_shape
                errors[field] = (
                    float(np.max(np.abs(reference_value - candidate_value)))
                    if same_shape
                    else None
                )

            metadata_equal = (
                reference.planner_status == candidate.planner_status
                and reference.failure_prediction == candidate.failure_prediction
            )
            equivalent = metadata_equal and all(shapes.values()) and all(
                error is not None and error <= self.absolute_tolerance
                for error in errors.values()
            )
            candidate_error_type = None
        except Exception as error:
            # A diagnostic-only candidate must never interrupt the authoritative
            # observation/control path. Record only the bounded exception type.
            errors = {field: None for field in ARRAY_FIELDS}
            shapes = {field: False for field in ARRAY_FIELDS}
            metadata_equal = False
            equivalent = False
            candidate_error_type = type(error).__name__
        return ObservationShadowResult(
            equivalent=equivalent,
            field_max_abs_error=errors,
            shape_equal=shapes,
            metadata_equal=metadata_equal,
            absolute_tolerance=self.absolute_tolerance,
            candidate_error_type=candidate_error_type,
        )


class ObservationShadowAccumulator:
    """Bounded aggregate suitable for later diagnostic-only runtime logging."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.comparison_count = 0
        self.equivalent_count = 0
        self.disabled_skip_count = 0
        self.metadata_mismatch_count = 0
        self.candidate_error_count = 0
        self.last_candidate_error_type: str | None = None
        self.field_mismatch_counts = {field: 0 for field in ARRAY_FIELDS}
        self.field_max_abs_error = {field: 0.0 for field in ARRAY_FIELDS}

    def record(self, result: ObservationShadowResult | None) -> None:
        with self._lock:
            if result is None:
                self.disabled_skip_count += 1
                return
            self.comparison_count += 1
            self.equivalent_count += int(result.equivalent)
            self.metadata_mismatch_count += int(not result.metadata_equal)
            if result.candidate_error_type is not None:
                self.candidate_error_count += 1
                self.last_candidate_error_type = result.candidate_error_type
            for field in ARRAY_FIELDS:
                error = result.field_max_abs_error[field]
                mismatch = not result.shape_equal[field] or error is None
                if error is not None:
                    self.field_max_abs_error[field] = max(
                        self.field_max_abs_error[field], error
                    )
                    mismatch = mismatch or error > result.absolute_tolerance
                self.field_mismatch_counts[field] += int(mismatch)

    def as_dict(self) -> dict[str, object]:
        with self._lock:
            return {
                "comparison_count": self.comparison_count,
                "equivalent_count": self.equivalent_count,
                "mismatch_count": self.comparison_count - self.equivalent_count,
                "disabled_skip_count": self.disabled_skip_count,
                "metadata_mismatch_count": self.metadata_mismatch_count,
                "candidate_error_count": self.candidate_error_count,
                "last_candidate_error_type": self.last_candidate_error_type,
                "field_mismatch_counts": self.field_mismatch_counts.copy(),
                "field_max_abs_error": self.field_max_abs_error.copy(),
                "stored_per_sample_records": 0,
                "authoritative_path_changed": False,
            }
