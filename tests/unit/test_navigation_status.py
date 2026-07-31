from __future__ import annotations

import pytest
from ramp_core.evaluation.navigation import (
    ConsecutiveEvidenceTracker,
    PlannerAbortTracker,
    navigation_status_is_active,
    timeout_is_invalid_reset,
)


def test_collision_evidence_requires_consecutive_frames() -> None:
    tracker = ConsecutiveEvidenceTracker(confirmation_frames=2)
    assert not tracker.update(True)
    assert not tracker.update(False)
    assert not tracker.update(True)
    assert tracker.update(True)


def test_collision_evidence_rejects_empty_confirmation_window() -> None:
    with pytest.raises(ValueError, match="positive"):
        ConsecutiveEvidenceTracker(confirmation_frames=0)


def test_navigation_activation_ignores_stale_terminal_goals() -> None:
    assert navigation_status_is_active((6, 2))
    assert navigation_status_is_active((1,))
    assert not navigation_status_is_active((4, 6))
    assert not navigation_status_is_active(())


def test_abort_requires_full_grace_without_active_replacement() -> None:
    tracker = PlannerAbortTracker(grace_s=5.0)
    assert not tracker.update(statuses=(2,), simulated_time_s=1.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=2.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=6.9)
    assert tracker.update(statuses=(6,), simulated_time_s=7.0)


def test_active_replacement_suppresses_stale_aborted_goal() -> None:
    tracker = PlannerAbortTracker(grace_s=2.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=1.0)
    assert not tracker.update(statuses=(6, 2), simulated_time_s=4.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=5.0)
    assert tracker.update(statuses=(6,), simulated_time_s=7.0)


def test_non_abort_and_clock_rewind_reset_or_restart_window() -> None:
    tracker = PlannerAbortTracker(grace_s=1.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=10.0)
    assert not tracker.update(statuses=(4,), simulated_time_s=12.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=20.0)
    assert not tracker.update(statuses=(6,), simulated_time_s=19.0)
    assert tracker.update(statuses=(6,), simulated_time_s=20.0)


def test_negative_abort_grace_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        PlannerAbortTracker(grace_s=-0.1)


def test_timeout_without_active_goal_or_movement_is_invalid_reset() -> None:
    assert timeout_is_invalid_reset(
        planner_ever_active=False,
        maximum_start_displacement_m=0.0,
    )
    assert not timeout_is_invalid_reset(
        planner_ever_active=True,
        maximum_start_displacement_m=0.0,
    )
    assert not timeout_is_invalid_reset(
        planner_ever_active=False,
        maximum_start_displacement_m=0.1,
    )
