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
    BoundedBackupOption,
    ObservableNetRetreatGuard,
    ObservableSubgoalStallGuard,
    PrivilegedYieldOption,
    constrain_net_retreat,
    constrain_recurrent_yield_escape,
    constrain_rejoin_actions,
    constrain_repeated_backup,
    constrain_repeated_replan,
    constrain_stalled_rejoin,
    constrain_stalled_subgoals,
    constrain_stalled_wait,
    ensure_safe_wait_fallback,
    should_continue_recovery_option,
)
from ramp_core.types import Pose2D


def test_bounded_backup_holds_then_releases_on_observable_clearance_gain() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=0.79,
        start_clearance_m=0.50,
        current_clearance_m=0.90,
    )
    assert option.is_complete(
        elapsed_s=0.80,
        start_clearance_m=0.50,
        current_clearance_m=0.75,
    )


def test_bounded_backup_runs_to_hard_limit_without_clearance_gain() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=2.99,
        start_clearance_m=0.50,
        current_clearance_m=0.74,
    )
    assert option.is_complete(
        elapsed_s=3.0,
        start_clearance_m=0.50,
        current_clearance_m=0.50,
    )


def test_bounded_backup_missing_observation_cannot_release_early() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=2.0,
        start_clearance_m=0.50,
        current_clearance_m=None,
    )
    assert option.is_complete(
        elapsed_s=3.0,
        start_clearance_m=None,
        current_clearance_m=None,
    )


def test_bounded_backup_maximum_matches_mask_validated_segment() -> None:
    option = BoundedBackupOption(
        speed_mps=0.15,
        maximum_duration_s=3.0,
        mask_validated_distance_m=0.45,
    )
    assert option.maximum_command_distance_m == pytest.approx(0.45)


def test_bounded_backup_rejects_motion_beyond_mask_validated_segment() -> None:
    with pytest.raises(ValueError, match="exceeds the action-mask"):
        BoundedBackupOption(
            speed_mps=0.15,
            maximum_duration_s=3.01,
            mask_validated_distance_m=0.45,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_duration_s": -0.1},
        {"minimum_duration_s": 1.0, "maximum_duration_s": 0.9},
        {"clearance_improvement_m": -0.1},
        {"speed_mps": float("nan")},
    ],
)
def test_bounded_backup_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        BoundedBackupOption(**kwargs)


def test_observable_retreat_guard_uses_task_progress_high_water_mark() -> None:
    guard = ObservableNetRetreatGuard(task_heading_rad=0.0, maximum_net_retreat_m=1.4)
    assert guard.backup_permitted(Pose2D(5.0, 12.0, 0.0), backup_distance_m=0.45)
    assert guard.observe(Pose2D(8.0, 12.0, 0.0)) == pytest.approx(0.0)
    assert guard.backup_permitted(Pose2D(7.1, 12.0, 0.0), backup_distance_m=0.45)
    assert not guard.backup_permitted(Pose2D(7.0, 12.0, 0.0), backup_distance_m=0.45)


def test_observable_retreat_guard_allows_backup_that_advances_task_progress() -> None:
    guard = ObservableNetRetreatGuard(task_heading_rad=0.0, maximum_net_retreat_m=1.4)
    guard.observe(Pose2D(8.0, 12.0, 0.0))
    # When facing opposite the task heading, reverse motion increases the task
    # coordinate and therefore cannot violate a net-retreat cap.
    assert guard.backup_permitted(Pose2D(6.5, 12.0, np.pi), backup_distance_m=0.45)


def test_net_retreat_constraint_only_removes_backup() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_net_retreat(
        mask,
        guard=guard,
        pose=Pose2D(7.0, 12.0, 0.0),
        backup_distance_m=0.45,
    )
    expected = mask.copy()
    expected[BACKUP_ACTION_ID] = False
    assert np.array_equal(constrained, expected)


def test_net_retreat_constraint_blocks_backward_facing_subgoals() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_net_retreat(
        mask,
        guard=guard,
        pose=Pose2D(7.0, 12.0, np.pi),
        backup_distance_m=0.45,
    )
    assert not bool(constrained[3])
    assert bool(constrained[0])
    assert bool(constrained[6])
    assert constrained[WAIT_ACTION_ID]


def test_retreat_guard_can_bound_optional_emergency_backup_pulse() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    assert guard.backup_permitted(Pose2D(6.8, 12.0, 0.0), backup_distance_m=0.12)
    assert not guard.backup_permitted(Pose2D(6.7, 12.0, 0.0), backup_distance_m=0.12)


def test_stationary_subgoal_retries_require_non_subgoal_escape() -> None:
    guard = ObservableSubgoalStallGuard(retry_budget=3, minimum_displacement_m=0.08)
    pose = Pose2D(2.0, 1.0, 0.0)
    for _ in range(3):
        guard.observe_decision(6, pose)
    assert guard.escape_required
    mask = constrain_stalled_subgoals(np.ones(ACTION_COUNT, dtype=np.bool_), escape_required=True)
    assert not mask[:WAIT_ACTION_ID].any()
    assert mask[WAIT_ACTION_ID]
    assert mask[BACKUP_ACTION_ID]
    guard.observe_decision(BACKUP_ACTION_ID, pose)
    assert not guard.escape_required


def test_subgoal_motion_resets_stationary_retry_count() -> None:
    guard = ObservableSubgoalStallGuard(retry_budget=3, minimum_displacement_m=0.08)
    guard.observe_decision(6, Pose2D(2.0, 1.0, 0.0))
    guard.observe_decision(6, Pose2D(2.1, 1.0, 0.0))
    guard.observe_decision(6, Pose2D(2.1, 1.0, 0.0))
    assert not guard.escape_required


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retry_budget": 0},
        {"minimum_displacement_m": -0.1},
        {"minimum_displacement_m": float("nan")},
    ],
)
def test_subgoal_stall_guard_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ObservableSubgoalStallGuard(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_heading_rad": float("nan")},
        {"task_heading_rad": 0.0, "maximum_net_retreat_m": 0.0},
        {"task_heading_rad": 0.0, "maximum_net_retreat_m": float("inf")},
    ],
)
def test_observable_retreat_guard_rejects_invalid_configuration(
    kwargs: dict[str, float],
) -> None:
    with pytest.raises(ValueError):
        ObservableNetRetreatGuard(**kwargs)


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


def test_empty_action_mask_fails_closed_to_wait_only() -> None:
    constrained = ensure_safe_wait_fallback(np.zeros(ACTION_COUNT, dtype=np.bool_))
    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[WAIT_ACTION_ID] = True
    assert np.array_equal(constrained, expected)


def test_safe_wait_fallback_does_not_weaken_nonempty_mask() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[REPLAN_ACTION_ID] = True
    constrained = ensure_safe_wait_fallback(mask)
    assert np.array_equal(constrained, mask)
    assert constrained is not mask


def test_composed_budgets_preserve_wait_when_later_bounds_remove_escape() -> None:
    """Regression for the runtime empty-mask failure seen in timeout v10."""
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[WAIT_ACTION_ID] = True
    mask[BACKUP_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True

    # Repetition budgets first remove REPLAN and BACKUP because the subgoal
    # still appears executable.  The net-retreat guard then rejects that last
    # translational escape.  WAIT must be evaluated only after those bounds.
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    constrained = constrain_repeated_backup(constrained, backup_count=2, backup_budget=2)
    constrained = constrain_net_retreat(
        constrained,
        guard=ObservableNetRetreatGuard(
            task_heading_rad=0.0,
            maximum_net_retreat_m=1.4,
            best_task_coordinate_m=8.0,
        ),
        pose=Pose2D(7.0, 12.0, np.pi),
        backup_distance_m=0.45,
    )
    constrained = constrain_stalled_wait(
        constrained,
        consecutive_waits=3,
        wait_budget=3,
    )
    constrained = ensure_safe_wait_fallback(constrained)

    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[WAIT_ACTION_ID] = True
    assert np.array_equal(constrained, expected)


def test_safe_wait_fallback_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match="mask must have shape"):
        ensure_safe_wait_fallback(np.zeros(ACTION_COUNT - 1, dtype=np.bool_))


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
