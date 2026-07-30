from __future__ import annotations

import numpy as np
import pytest
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
    RecoveryActionKind,
)
from ramp_core.observations import RecoveryObservation
from ramp_core.recovery.heuristic import HeuristicRecoveryConfig, HeuristicRecoveryPolicy
from ramp_core.types import FailurePrediction, PlannerStatus


def _observation(
    failure: FailurePrediction,
    *,
    left_clearance: float = 3.0,
    right_clearance: float = 3.0,
    front_clearance: float | None = None,
    planner_status: PlannerStatus = PlannerStatus.ACTIVE,
    progress: float = 0.0,
) -> RecoveryObservation:
    lidar = np.empty((5, 180), dtype=np.float32)
    lidar[:, :90] = right_clearance
    lidar[:, 90:] = left_clearance
    if front_clearance is not None:
        lidar[:, 75:106] = front_clearance
    waypoints = np.zeros((8, 2), dtype=np.float32)
    waypoints[:, 0] = np.linspace(0.25, 2.0, 8)
    return RecoveryObservation(
        lidar=lidar,
        goal_polar=np.asarray([5.0, 0.0], dtype=np.float32),
        path_waypoints=waypoints,
        robot_velocity=np.zeros(2, dtype=np.float32),
        base_action=np.zeros(2, dtype=np.float32),
        progress_history=np.linspace(progress, 0.0, 10, dtype=np.float32),
        angular_velocity_history=np.zeros(10, dtype=np.float32),
        planner_status=planner_status,
        failure_prediction=failure,
    )


def _full_mask() -> np.ndarray:
    return np.ones(ACTION_COUNT, dtype=np.bool_)


def test_collision_risk_waits_when_side_clearance_is_similar() -> None:
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(FailurePrediction(1.0, 0.0, 0.0, 0.0)), _full_mask()
    )
    assert decision.action_id == WAIT_ACTION_ID
    assert decision.reason == "collision_imminent_wait"


def test_collision_risk_chooses_clear_legal_side() -> None:
    mask = _full_mask()
    mask[17] = False  # Preferred 1.4 m/+30 deg action must remain masked.
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(
            FailurePrediction(1.0, 0.0, 0.0, 0.0),
            left_clearance=4.0,
            right_clearance=1.0,
            front_clearance=3.0,
        ),
        mask,
    )
    action = ACTIONS[decision.action_id]
    assert mask[decision.action_id]
    assert action.kind is RecoveryActionKind.SUBGOAL
    assert action.angle_degrees is not None and action.angle_degrees > 0


def test_imminent_collision_waits_even_when_one_side_is_clearer() -> None:
    policy = HeuristicRecoveryPolicy()
    decision = policy.select_action(
        _observation(
            FailurePrediction(1.0, 0.0, 0.0, 0.0),
            left_clearance=4.0,
            right_clearance=1.0,
            front_clearance=0.8,
        ),
        _full_mask(),
    )
    assert decision.action_id == WAIT_ACTION_ID
    assert decision.reason == "collision_imminent_wait"

    followup = policy.select_action(
        _observation(
            FailurePrediction(1.0, 0.0, 0.0, 0.0),
            left_clearance=4.0,
            right_clearance=1.0,
            front_clearance=0.8,
        ),
        _full_mask(),
    )
    assert followup.action_id == BACKUP_ACTION_ID
    assert followup.reason == "collision_persistent_close_backup"


def test_persistent_close_lateral_hazard_uses_backup_before_slow_subgoal() -> None:
    policy = HeuristicRecoveryPolicy()
    first = _observation(
        FailurePrediction(1.0, 0.0, 0.0, 0.0),
        left_clearance=3.0,
        right_clearance=3.0,
        front_clearance=2.0,
    )
    assert policy.select_action(first, _full_mask()).action_id == WAIT_ACTION_ID
    lateral_close = _observation(
        FailurePrediction(1.0, 0.0, 0.0, 0.0),
        left_clearance=3.0,
        right_clearance=0.55,
        front_clearance=2.0,
    )
    decision = policy.select_action(lateral_close, _full_mask())
    assert decision.action_id == BACKUP_ACTION_ID
    assert decision.reason == "collision_persistent_close_backup"


def test_close_side_wall_does_not_force_persistent_backup() -> None:
    policy = HeuristicRecoveryPolicy()
    observation = _observation(
        FailurePrediction(1.0, 0.0, 0.0, 0.0),
        left_clearance=0.7,
        right_clearance=2.0,
        front_clearance=1.4,
    )
    first = policy.select_action(observation, _full_mask())
    second = policy.select_action(observation, _full_mask())
    assert ACTIONS[first.action_id].kind is RecoveryActionKind.SUBGOAL
    assert ACTIONS[second.action_id].kind is RecoveryActionKind.SUBGOAL


def test_freeze_prefers_backup_then_path_aligned_subgoal() -> None:
    observation = _observation(FailurePrediction(0.0, 1.0, 0.0, 0.0))
    policy = HeuristicRecoveryPolicy()
    assert policy.select_action(observation, _full_mask()).action_id == BACKUP_ACTION_ID

    assert policy.select_action(observation, _full_mask()).action_id == BACKUP_ACTION_ID
    followup = policy.select_action(
        _observation(
            FailurePrediction(0.0, 1.0, 0.0, 0.0),
            front_clearance=3.0,
        ),
        _full_mask(),
    )
    assert ACTIONS[followup.action_id].kind is RecoveryActionKind.SUBGOAL
    assert ACTIONS[followup.action_id].angle_degrees == 0

    mask = _full_mask()
    mask[BACKUP_ACTION_ID] = False
    decision = HeuristicRecoveryPolicy().select_action(observation, mask)
    action = ACTIONS[decision.action_id]
    assert action.kind is RecoveryActionKind.SUBGOAL
    assert action.angle_degrees == 0
    assert action.radius == pytest.approx(1.0)


def test_freeze_chooses_stable_side_after_backing_from_blocked_front() -> None:
    policy = HeuristicRecoveryPolicy()
    observation = _observation(
        FailurePrediction(0.0, 1.0, 0.0, 0.0),
        left_clearance=4.0,
        right_clearance=1.0,
        front_clearance=0.8,
    )
    assert policy.select_action(observation, _full_mask()).action_id == BACKUP_ACTION_ID
    assert policy.select_action(observation, _full_mask()).action_id == BACKUP_ACTION_ID
    decision = policy.select_action(observation, _full_mask())
    assert decision.reason == "freeze_blocked_choose_side"
    assert ACTIONS[decision.action_id].angle_degrees is not None
    assert ACTIONS[decision.action_id].angle_degrees > 0


def test_zero_progress_side_subgoals_are_rejected_for_more_backup() -> None:
    policy = HeuristicRecoveryPolicy()
    observation = _observation(
        FailurePrediction(0.0, 1.0, 0.0, 0.0),
        front_clearance=0.8,
    )
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[6] = True  # 0.6 m / +90 degrees has zero goal projection.
    mask[BACKUP_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True
    assert policy.select_action(observation, mask).action_id == BACKUP_ACTION_ID
    assert policy.select_action(observation, mask).action_id == BACKUP_ACTION_ID
    decision = policy.select_action(observation, mask)
    assert decision.action_id == BACKUP_ACTION_ID
    assert decision.reason == "freeze_clearance_backup"


def test_scored_subgoal_prefers_forward_progress_over_lateral_motion() -> None:
    policy = HeuristicRecoveryPolicy()
    observation = _observation(
        FailurePrediction(0.0, 1.0, 0.0, 0.0),
        left_clearance=4.0,
        right_clearance=1.0,
        front_clearance=0.8,
    )
    policy.select_action(observation, _full_mask())
    policy.select_action(observation, _full_mask())
    decision = policy.select_action(observation, _full_mask())
    action = ACTIONS[decision.action_id]
    assert action.angle_degrees is not None
    assert 0 < action.angle_degrees < 90
    assert action.radius is not None
    projected_progress = action.radius * np.cos(np.deg2rad(action.angle_degrees))
    assert projected_progress >= policy.config.minimum_subgoal_progress_m


def test_low_score_stalled_rejoin_uses_side_subgoal() -> None:
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(
            FailurePrediction(0.0, 0.0, 0.0, 0.0),
            left_clearance=4.0,
            right_clearance=1.0,
            progress=0.0,
        ),
        _full_mask(),
    )
    assert decision.reason == "stalled_rejoin_side_subgoal"
    assert ACTIONS[decision.action_id].angle_degrees is not None
    assert ACTIONS[decision.action_id].angle_degrees > 0


def test_oscillation_side_cooldown_prevents_immediate_flip() -> None:
    policy = HeuristicRecoveryPolicy(HeuristicRecoveryConfig(side_cooldown_decisions=4))
    failure = FailurePrediction(0.0, 0.0, 1.0, 0.0)
    first = policy.select_action(
        _observation(failure, left_clearance=4.0, right_clearance=1.0), _full_mask()
    )
    second = policy.select_action(
        _observation(failure, left_clearance=1.0, right_clearance=4.0), _full_mask()
    )
    assert ACTIONS[first.action_id].angle_degrees is not None
    assert ACTIONS[second.action_id].angle_degrees is not None
    assert ACTIONS[first.action_id].angle_degrees > 0
    assert ACTIONS[second.action_id].angle_degrees > 0


def test_deadlock_escalates_from_wait_to_backup_to_replan() -> None:
    policy = HeuristicRecoveryPolicy(
        HeuristicRecoveryConfig(
            deadlock_backup_after_decisions=2,
            deadlock_replan_after_decisions=4,
        )
    )
    observation = _observation(FailurePrediction(0.0, 0.0, 0.0, 1.0))
    mask = _full_mask()
    decisions = [policy.select_action(observation, mask).action_id for _ in range(4)]
    assert decisions == [WAIT_ACTION_ID, BACKUP_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID]


def test_planner_failure_prefers_path_subgoal_before_replan() -> None:
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(
            FailurePrediction(0.0, 0.0, 0.0, 0.0),
            planner_status=PlannerStatus.ABORTED,
        ),
        _full_mask(),
    )
    assert ACTIONS[decision.action_id].kind is RecoveryActionKind.SUBGOAL
    assert ACTIONS[decision.action_id].angle_degrees == 0
    assert decision.reason == "planner_failure_path_subgoal"

    mask = _full_mask()
    mask[:21] = False
    fallback = HeuristicRecoveryPolicy().select_action(
        _observation(
            FailurePrediction(0.0, 0.0, 0.0, 0.0),
            planner_status=PlannerStatus.ABORTED,
        ),
        mask,
    )
    assert fallback.action_id == REPLAN_ACTION_ID
    assert fallback.reason == "planner_failure_replan"


def test_detected_freeze_takes_priority_over_transient_planner_abort() -> None:
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(
            FailurePrediction(0.0, 1.0, 0.0, 0.0),
            planner_status=PlannerStatus.ABORTED,
        ),
        _full_mask(),
    )
    assert decision.action_id == BACKUP_ACTION_ID
    assert decision.reason == "freeze_backup"


def test_fallback_never_selects_masked_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    decision = HeuristicRecoveryPolicy().select_action(
        _observation(FailurePrediction(0.0, 1.0, 0.0, 0.0)), mask
    )
    assert decision.action_id == WAIT_ACTION_ID


def test_empty_action_mask_is_rejected() -> None:
    with pytest.raises(ValueError, match="no valid action"):
        HeuristicRecoveryPolicy().select_action(
            _observation(FailurePrediction(1.0, 0.0, 0.0, 0.0)),
            np.zeros(ACTION_COUNT, dtype=np.bool_),
        )
