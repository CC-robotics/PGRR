from __future__ import annotations

from ramp_core.types import PlannerStatus, select_planner_status


def test_active_planner_status_wins_over_stale_terminal_entries() -> None:
    selected = select_planner_status(
        [PlannerStatus.SUCCEEDED, PlannerStatus.ACTIVE, PlannerStatus.ABORTED]
    )
    assert selected is PlannerStatus.ACTIVE


def test_planner_status_uses_last_terminal_when_none_are_active() -> None:
    selected = select_planner_status([PlannerStatus.SUCCEEDED, PlannerStatus.ABORTED])
    assert selected is PlannerStatus.ABORTED
    assert select_planner_status([]) is PlannerStatus.UNKNOWN
