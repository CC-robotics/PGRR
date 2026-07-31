from __future__ import annotations

import math

import pytest
from ramp_core.planning.rollout import yielding_human_step


def test_human_holds_before_entering_robot_avoidance_radius() -> None:
    assert yielding_human_step((0.0, 0.0), (1.4, 0.0), (1.2, 0.0), 1.3) == (1.4, 0.0)


def test_human_inside_avoidance_radius_can_move_away() -> None:
    assert yielding_human_step((0.0, 0.0), (1.0, 0.0), (1.1, 0.0), 1.3) == (1.1, 0.0)


def test_human_inside_avoidance_radius_cannot_move_closer() -> None:
    assert yielding_human_step((0.0, 0.0), (1.0, 0.0), (0.9, 0.0), 1.3) == (1.0, 0.0)


def test_zero_avoidance_distance_disables_yielding() -> None:
    assert yielding_human_step((0.0, 0.0), (0.5, 0.0), (0.4, 0.0), 0.0) == (0.4, 0.0)


@pytest.mark.parametrize("distance", [-0.1, math.inf, math.nan])
def test_human_yield_rejects_invalid_avoidance_distance(distance: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        yielding_human_step((0.0, 0.0), (1.0, 0.0), (0.9, 0.0), distance)
