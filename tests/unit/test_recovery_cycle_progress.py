from __future__ import annotations

import pytest
from ramp_core.recovery.progress import (
    RecoveryCycleEvidence,
    RecoveryCycleProgressConfig,
    RecoveryCycleVerdict,
    assess_recovery_cycle,
)

CONFIG = RecoveryCycleProgressConfig(
    minimum_original_goal_progress_m=0.2,
    minimum_clear_frames=4,
    rapid_retrigger_window_s=3.0,
)


def _evidence(**overrides: object) -> RecoveryCycleEvidence:
    values = {
        "start_original_goal_distance_m": 10.0,
        "end_original_goal_distance_m": 9.5,
        "consecutive_clear_frames": 4,
        "original_goal_active": True,
        "retrigger_delay_s": None,
        "retrigger_observation_s": 5.0,
    }
    values.update(overrides)
    return RecoveryCycleEvidence(**values)  # type: ignore[arg-type]


def test_effective_cycle_satisfies_every_observable_check() -> None:
    result = assess_recovery_cycle(_evidence(), CONFIG)

    assert result.verdict is RecoveryCycleVerdict.EFFECTIVE
    assert result.effective
    assert result.original_goal_progress_m == pytest.approx(0.5)
    assert result.hazard_cleared
    assert result.meaningful_task_progress
    assert not result.rapid_retrigger


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"original_goal_active": False}, RecoveryCycleVerdict.ORIGINAL_GOAL_NOT_ACTIVE),
        ({"consecutive_clear_frames": 3}, RecoveryCycleVerdict.HAZARD_NOT_CLEARED),
        (
            {"end_original_goal_distance_m": 9.81},
            RecoveryCycleVerdict.INSUFFICIENT_TASK_PROGRESS,
        ),
        ({"retrigger_delay_s": 3.0}, RecoveryCycleVerdict.RAPID_RETRIGGER),
        (
            {"retrigger_observation_s": 2.9},
            RecoveryCycleVerdict.RETRIGGER_OBSERVATION_INCOMPLETE,
        ),
    ],
)
def test_cycle_verdict_reports_first_unmet_contract(
    overrides: dict[str, object], expected: RecoveryCycleVerdict
) -> None:
    result = assess_recovery_cycle(_evidence(**overrides), CONFIG)

    assert result.verdict is expected
    assert not result.effective


def test_retreat_is_not_task_progress() -> None:
    result = assess_recovery_cycle(
        _evidence(end_original_goal_distance_m=10.4),
        CONFIG,
    )

    assert result.original_goal_progress_m == pytest.approx(-0.4)
    assert result.verdict is RecoveryCycleVerdict.INSUFFICIENT_TASK_PROGRESS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_original_goal_progress_m": 0.0},
        {"minimum_clear_frames": 0},
        {"rapid_retrigger_window_s": -0.1},
    ],
)
def test_config_rejects_invalid_thresholds(kwargs: dict[str, float | int]) -> None:
    values: dict[str, float | int] = {
        "minimum_original_goal_progress_m": 0.2,
        "minimum_clear_frames": 4,
        "rapid_retrigger_window_s": 3.0,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        RecoveryCycleProgressConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_original_goal_distance_m": -0.1},
        {"end_original_goal_distance_m": float("nan")},
        {"consecutive_clear_frames": -1},
        {"retrigger_delay_s": -0.1},
        {"retrigger_observation_s": -0.1},
        {"retrigger_delay_s": 4.0, "retrigger_observation_s": 3.0},
    ],
)
def test_evidence_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _evidence(**overrides)
