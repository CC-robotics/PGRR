from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from ramp_core.observations import RecoveryObservation
from ramp_core.recovery.observation_shadow import (
    ObservationShadowAccumulator,
    ObservationShadowComparator,
)
from ramp_core.types import FailurePrediction, PlannerStatus


def _observation(*, base_linear: float = 0.2) -> RecoveryObservation:
    return RecoveryObservation(
        lidar=np.ones((5, 180), dtype=np.float32),
        goal_polar=np.asarray([2.0, 0.1], dtype=np.float32),
        path_waypoints=np.zeros((8, 2), dtype=np.float32),
        robot_velocity=np.asarray([0.1, 0.0], dtype=np.float32),
        base_action=np.asarray([base_linear, 0.0], dtype=np.float32),
        progress_history=np.ones(10, dtype=np.float32),
        angular_velocity_history=np.zeros(10, dtype=np.float32),
        planner_status=PlannerStatus.ACTIVE,
        failure_prediction=FailurePrediction(0.1, 0.2, 0.3, 0.4),
    )


def test_disabled_shadow_does_not_evaluate_candidate() -> None:
    called = False

    def candidate() -> RecoveryObservation:
        nonlocal called
        called = True
        raise AssertionError("disabled shadow evaluated its candidate")

    result = ObservationShadowComparator().compare(_observation(), candidate)

    assert result is None
    assert called is False


def test_enabled_shadow_reports_exact_equivalence_without_authority_change() -> None:
    reference = _observation()
    result = ObservationShadowComparator(enabled=True).compare(reference, lambda: reference)

    assert result is not None
    assert result.equivalent
    assert all(value == 0.0 for value in result.field_max_abs_error.values())
    assert result.as_dict()["authoritative_path_changed"] is False


def test_enabled_shadow_detects_field_difference() -> None:
    result = ObservationShadowComparator(enabled=True).compare(
        _observation(), lambda: _observation(base_linear=0.25)
    )

    assert result is not None
    assert not result.equivalent
    assert result.field_max_abs_error["base_action"] == pytest.approx(0.05)


def test_enabled_shadow_contains_candidate_error_and_preserves_reference() -> None:
    reference = _observation()

    def broken_candidate() -> RecoveryObservation:
        raise RuntimeError("diagnostic candidate failed")

    result = ObservationShadowComparator(enabled=True).compare(
        reference, broken_candidate
    )
    accumulator = ObservationShadowAccumulator()
    accumulator.record(result)
    summary = accumulator.as_dict()

    assert result is not None
    assert not result.equivalent
    assert result.candidate_error_type == "RuntimeError"
    assert result.as_dict()["authoritative_path_changed"] is False
    assert summary["candidate_error_count"] == 1
    assert summary["last_candidate_error_type"] == "RuntimeError"
    assert summary["stored_per_sample_records"] == 0


def test_accumulator_is_bounded_and_counts_disabled_exact_and_mismatch() -> None:
    comparator = ObservationShadowComparator(enabled=True)
    exact = comparator.compare(_observation(), _observation)
    mismatch = comparator.compare(_observation(), lambda: _observation(base_linear=0.25))
    accumulator = ObservationShadowAccumulator()

    accumulator.record(None)
    accumulator.record(exact)
    accumulator.record(mismatch)
    summary = accumulator.as_dict()

    assert summary["comparison_count"] == 2
    assert summary["equivalent_count"] == 1
    assert summary["mismatch_count"] == 1
    assert summary["disabled_skip_count"] == 1
    assert summary["field_mismatch_counts"]["base_action"] == 1
    assert summary["stored_per_sample_records"] == 0
    assert summary["authoritative_path_changed"] is False


def test_accumulator_is_thread_safe_and_returns_detached_snapshots() -> None:
    comparator = ObservationShadowComparator(enabled=True)
    exact = comparator.compare(_observation(), _observation)
    mismatch = comparator.compare(
        _observation(), lambda: _observation(base_linear=0.25)
    )
    accumulator = ObservationShadowAccumulator()
    workload = [exact] * 400 + [mismatch] * 300 + [None] * 300

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(accumulator.record, workload))

    summary = accumulator.as_dict()
    assert summary["comparison_count"] == 700
    assert summary["equivalent_count"] == 400
    assert summary["mismatch_count"] == 300
    assert summary["disabled_skip_count"] == 300
    assert summary["field_mismatch_counts"]["base_action"] == 300

    summary["field_mismatch_counts"]["base_action"] = -1
    summary["field_max_abs_error"]["base_action"] = -1.0
    fresh = accumulator.as_dict()
    assert fresh["field_mismatch_counts"]["base_action"] == 300
    assert fresh["field_max_abs_error"]["base_action"] == pytest.approx(0.05)


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_shadow_rejects_invalid_tolerance(value: float) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        ObservationShadowComparator(absolute_tolerance=value)
