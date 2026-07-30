from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    CONTINUE_ACTION_ID,
    WAIT_ACTION_ID,
    RecoveryActionKind,
)
from ramp_core.observations import HumanState, PrivilegedState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.expert import PlanningRecoveryExpert
from ramp_core.planning.rollout import rollout_action
from ramp_core.types import Pose2D, Velocity2D


def _grid() -> OccupancyGrid:
    return OccupancyGrid(np.zeros((120, 120), dtype=np.bool_), 0.1, -3.0, -3.0)


def _state(*humans: HumanState, yaw: float = 0.0) -> PrivilegedState:
    return PrivilegedState(
        robot_pose=Pose2D(0.0, 0.0, yaw),
        robot_velocity=Velocity2D(0.0, 0.0),
        original_goal=Pose2D(5.0, 0.0, 0.0),
        global_path=tuple((index * 0.1, 0.0) for index in range(51)),
        humans=humans,
        time_step=0.1,
    )


def _mask() -> np.ndarray:
    return np.ones(ACTION_COUNT, dtype=np.bool_)


def test_expert_never_selects_masked_action_and_reports_margin() -> None:
    mask = _mask()
    mask[:20] = False
    label = PlanningRecoveryExpert(_grid()).label(_state(), mask)
    assert mask[label.action_id]
    assert np.all(np.isinf(label.action_costs[~mask]))
    assert label.best_cost <= label.second_best_cost
    assert label.margin == pytest.approx(label.second_best_cost - label.best_cost)


def test_empty_scene_selects_progressive_action_instead_of_wait() -> None:
    label = PlanningRecoveryExpert(_grid()).label(_state(), _mask())
    assert label.action_id != WAIT_ACTION_ID
    assert label.predicted_success


def test_head_on_human_makes_continue_rollout_collide() -> None:
    human = HumanState(position=(1.3, 0.0), velocity=(-0.2, 0.0), radius=0.35)
    state = _state(human)
    rollout = rollout_action(state, ACTIONS[CONTINUE_ACTION_ID], _grid())
    label = PlanningRecoveryExpert(_grid()).label(state, _mask())
    assert rollout.collision
    assert label.action_id != CONTINUE_ACTION_ID
    assert label.action_costs[CONTINUE_ACTION_ID] >= 1_000_000.0


def test_human_approaching_from_left_does_not_choose_left_subgoal() -> None:
    human = HumanState(position=(0.6, 0.6), velocity=(0.0, -0.35), radius=0.35)
    label = PlanningRecoveryExpert(_grid()).label(_state(human), _mask())
    selected = ACTIONS[label.action_id]
    if selected.kind is RecoveryActionKind.SUBGOAL:
        assert selected.angle_degrees is not None
        assert selected.angle_degrees <= 0


def test_wait_is_not_free_when_nothing_blocks_progress() -> None:
    label = PlanningRecoveryExpert(_grid()).label(_state(), _mask())
    assert label.action_costs[WAIT_ACTION_ID] > label.best_cost


@pytest.mark.parametrize("angle_index", range(20))
def test_twenty_privileged_validation_states_produce_legal_finite_labels(
    angle_index: int,
) -> None:
    angle = -math.pi + angle_index * (2.0 * math.pi / 20.0)
    human = HumanState(
        position=(1.4 * math.cos(angle), 1.4 * math.sin(angle)),
        velocity=(-0.15 * math.cos(angle), -0.15 * math.sin(angle)),
        radius=0.35,
    )
    mask = _mask()
    mask[angle_index] = False
    label = PlanningRecoveryExpert(_grid()).label(_state(human), mask)
    assert mask[label.action_id]
    assert math.isfinite(label.best_cost)
    assert label.margin >= 0.0
