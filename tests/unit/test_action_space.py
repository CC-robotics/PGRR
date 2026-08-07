import math

import pytest
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
)
from ramp_core.types import Pose2D


def test_action_ids_and_special_actions_are_stable() -> None:
    assert len(ACTIONS) == ACTION_COUNT == 25
    assert [action.action_id for action in ACTIONS] == list(range(25))
    assert (WAIT_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID, CONTINUE_ACTION_ID) == (
        21,
        22,
        23,
        24,
    )


def test_forward_subgoal_generation() -> None:
    action = ACTIONS[3]
    target = action.target_pose(Pose2D(1.0, 2.0, math.pi / 2.0))
    assert target is not None
    assert (target.x, target.y) == pytest.approx((1.0, 2.6))
