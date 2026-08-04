from __future__ import annotations

import numpy as np
import pytest
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
    RecoveryActionKind,
)
from ramp_core.observations import HumanState
from ramp_core.recovery.options import (
    PrivilegedYieldOption,
    constrain_recurrent_yield_escape,
    constrain_rejoin_actions,
    constrain_repeated_backup,
    constrain_repeated_replan,
    constrain_stalled_rejoin,
    constrain_stalled_wait,
    should_continue_recovery_option,
)
from ramp_core.types import Pose2D


def _continue(**overrides: object) -> bool:
    values: dict[str, object] = {
        "policy_type": "expert",
        "action_id": WAIT_ACTION_ID,
        "action_complete": True,
        "failure_score": 0.0,
        "tau_off": 0.35,
        "option_elapsed_s": 2.0,
        "maximum_option_duration_s": 8.0,
    }
    values.update(overrides)
    return should_continue_recovery_option(**values)  # type: ignore[arg-type]


def test_expert_composes_completed_escape_actions_before_rejoin() -> None:
    assert _continue(action_id=WAIT_ACTION_ID)


def test_expert_continue_action_explicitly_requests_rejoin() -> None:
    assert not _continue(action_id=CONTINUE_ACTION_ID)


def test_observable_failure_keeps_any_policy_in_recovery() -> None:
    assert _continue(policy_type="heuristic", failure_score=0.8)


def test_option_duration_is_a_hard_bound() -> None:
    assert not _continue(option_elapsed_s=8.0)


def test_option_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError, match="lie in"):
        _continue(failure_score=1.1)


def test_collision_latch_masks_rejoin_but_preserves_wait() -> None:
    mask = constrain_rejoin_actions(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        collision_risk=0.75,
        release_threshold=0.35,
    )
    assert not mask[CONTINUE_ACTION_ID]
    assert not mask[REPLAN_ACTION_ID]
    assert mask[WAIT_ACTION_ID]


def test_cleared_collision_latch_restores_rejoin_actions() -> None:
    mask = constrain_rejoin_actions(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        collision_risk=0.0,
        release_threshold=0.35,
    )
    assert mask[CONTINUE_ACTION_ID]
    assert mask[REPLAN_ACTION_ID]


def test_stalled_rejoin_masks_continue_when_planned_escape_exists() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_rejoin(mask, escape_required=True)
    assert constrained[3]
    assert constrained[WAIT_ACTION_ID]
    assert not constrained[CONTINUE_ACTION_ID]


def test_stalled_rejoin_keeps_continue_when_wait_is_only_alternative() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_rejoin(mask, escape_required=True)
    assert constrained[WAIT_ACTION_ID]
    assert constrained[CONTINUE_ACTION_ID]


def test_wait_budget_forces_available_escape_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[BACKUP_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert not constrained[WAIT_ACTION_ID]
    assert constrained[BACKUP_ACTION_ID]


def test_wait_budget_treats_replan_as_an_escape() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert not constrained[WAIT_ACTION_ID]
    assert constrained[REPLAN_ACTION_ID]


def test_replan_budget_forces_an_available_alternative() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    assert constrained[WAIT_ACTION_ID]
    assert not constrained[REPLAN_ACTION_ID]


def test_replan_remains_when_it_is_the_only_legal_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    assert constrained[REPLAN_ACTION_ID]


def test_backup_budget_forces_planning_valid_subgoal() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[BACKUP_ACTION_ID] = True
    mask[WAIT_ACTION_ID] = True
    constrained = constrain_repeated_backup(mask, backup_count=2, backup_budget=2)
    assert constrained[3]
    assert not constrained[BACKUP_ACTION_ID]
    assert constrained[WAIT_ACTION_ID]


def test_backup_remains_when_no_planned_escape_is_safe() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[BACKUP_ACTION_ID] = True
    mask[WAIT_ACTION_ID] = True
    constrained = constrain_repeated_backup(mask, backup_count=2, backup_budget=2)
    assert constrained[BACKUP_ACTION_ID]


def test_wait_remains_valid_before_budget_is_exhausted() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_stalled_wait(mask, consecutive_waits=2, wait_budget=3)
    assert constrained[WAIT_ACTION_ID]


def test_wait_remains_valid_when_no_escape_is_safe() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert constrained[WAIT_ACTION_ID]


def test_privileged_yield_commits_until_threat_passes_longitudinally() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0, passed_margin_m=0.5)
    approaching = HumanState((1.5, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    assert option.backup_required
    stopped_ahead = HumanState((0.4, 0.0), (0.0, 0.0), 0.35)
    assert option.update(Pose2D(-0.5, 0.0, 0.0), (stopped_ahead,), collision_risk=False)
    assert option.backup_required
    assert option.update(Pose2D(-1.5, 0.0, 0.0), (stopped_ahead,), collision_risk=False)
    assert not option.backup_required
    passed = HumanState((-1.1, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)


def test_privileged_yield_ignores_nonapproaching_human() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    receding = HumanState((1.0, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (receding,), collision_risk=True)


def test_privileged_yield_releases_when_all_threats_reverse_away() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    approaching = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    reversed_route = HumanState((1.5, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(
        Pose2D(-1.0, 0.0, 0.0),
        (reversed_route,),
        collision_risk=False,
    )


def test_privileged_yield_escalates_when_flow_recurs_without_progress() -> None:
    option = PrivilegedYieldOption(
        task_heading_rad=0.0,
        recurrence_progress_m=0.75,
        maximum_recurrences_without_progress=1,
    )
    approaching = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    reversed_route = HumanState((1.5, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(
        Pose2D(-1.0, 0.0, 0.0),
        (reversed_route,),
        collision_risk=False,
    )
    returning = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(-0.8, 0.0, 0.0), (returning,), collision_risk=True)
    assert option.escape_required
    assert option.recurrence_count == 1


def test_privileged_yield_escalates_when_passed_human_cycles_back() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    approaching = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    passed = HumanState((-0.6, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)
    returning = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.2, 0.0, 0.0), (returning,), collision_risk=True)
    assert option.escape_required


def test_privileged_yield_does_not_escalate_after_robot_clears_window() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0, recurrence_progress_m=0.75)
    approaching = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    passed = HumanState((-0.6, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)
    next_flow = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(1.0, 0.0, 0.0), (next_flow,), collision_risk=True)
    assert not option.escape_required


def test_recurrent_yield_escape_preserves_only_lateral_and_replan_actions() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_recurrent_yield_escape(mask, escape_required=True)
    for action in ACTIONS:
        expected = (
            action.kind is RecoveryActionKind.SUBGOAL and action.angle_degrees != 0
        ) or action.action_id == REPLAN_ACTION_ID
        assert bool(constrained[action.action_id]) is expected


def test_recurrent_yield_escape_keeps_safe_fallback_without_escape_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    assert np.array_equal(
        constrain_recurrent_yield_escape(mask, escape_required=True),
        mask,
    )
