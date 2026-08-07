from __future__ import annotations

import math

import pytest
from ramp_core.planning.rollout import (
    collision_guarded_human_step,
    same_time_swept_clearance,
    yielding_human_step,
)


def test_same_time_swept_clearance_uses_synchronized_relative_motion() -> None:
    clearance = same_time_swept_clearance(
        (-1.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
    )
    assert clearance == pytest.approx(0.0)


def test_close_parallel_guard_safe_pass_is_not_blanket_frozen() -> None:
    decision = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (-0.5, 0.75),
        (0.5, 0.75),
        0.2,
    )
    assert decision.position == pytest.approx((0.5, 0.75))
    assert decision.progress_fraction == pytest.approx(1.0)
    assert decision.swept_clearance_m == pytest.approx(0.75)
    assert not decision.guard_intervened


def test_receding_endpoint_whose_sweep_crosses_guard_is_rejected() -> None:
    decision = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (-0.72, 0.0),
        (0.80, 0.0),
        0.2,
    )
    assert decision.position == pytest.approx((-0.72, 0.0))
    assert decision.progress_fraction == pytest.approx(0.0)
    assert decision.reason == "inside_guard_non_escaping_hold"
    assert decision.guard_intervened


def test_actor_already_inside_guard_can_strictly_escape() -> None:
    decision = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (0.72, 0.0),
        (0.82, 0.0),
        0.2,
    )
    assert decision.position == pytest.approx((0.82, 0.0))
    assert decision.progress_fraction == pytest.approx(1.0)
    assert decision.reason == "inside_guard_escape"


def test_hard_guard_truncates_to_a_continuously_safe_prefix() -> None:
    decision = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (1.0, 0.0),
        (0.5, 0.0),
        0.2,
        maximum_soft_hold_s=0.0,
    )
    assert 0.0 < decision.progress_fraction < 1.0
    assert decision.position[0] >= 0.73
    assert decision.swept_clearance_m >= 0.73 - 1.0e-9
    assert decision.reason == "hard_guard_truncated"


def test_soft_yield_hold_is_bounded_and_then_allows_safe_motion() -> None:
    held = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (1.0, 0.0),
        (0.8, 0.0),
        0.5,
    )
    assert held.reason == "soft_yield_hold"
    assert held.progress_fraction == 0.0
    released = collision_guarded_human_step(
        (0.0, 0.0),
        (0.0, 0.0),
        (1.0, 0.0),
        (0.8, 0.0),
        0.5,
        soft_hold_elapsed_s=1.0,
    )
    assert released.reason == "soft_yield_budget_exhausted"
    assert released.progress_fraction == 1.0


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("robot_position", (math.nan, 0.0)),
        ("robot_velocity", (math.inf, 0.0)),
        ("current_position", (0.0, math.nan)),
        ("candidate_position", (0.0, math.inf)),
    ],
)
def test_collision_guard_rejects_non_finite_positions(
    argument: str,
    value: tuple[float, float],
) -> None:
    arguments = {
        "robot_position": (0.0, 0.0),
        "robot_velocity": (0.0, 0.0),
        "current_position": (1.0, 0.0),
        "candidate_position": (0.9, 0.0),
    }
    arguments[argument] = value
    with pytest.raises(ValueError, match="finite"):
        collision_guarded_human_step(**arguments, step_duration_s=0.2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"step_duration_s": 0.0},
        {"soft_yield_distance_m": 0.72},
        {"hard_collision_guard_m": 0.0},
        {"maximum_soft_hold_s": -0.1},
        {"soft_hold_elapsed_s": -0.1},
        {"step_duration_s": math.nan},
    ],
)
def test_collision_guard_rejects_invalid_parameters(overrides: dict[str, float]) -> None:
    arguments = {
        "robot_position": (0.0, 0.0),
        "robot_velocity": (0.0, 0.0),
        "current_position": (1.0, 0.0),
        "candidate_position": (0.9, 0.0),
        "step_duration_s": 0.2,
    }
    arguments.update(overrides)
    with pytest.raises(ValueError):
        collision_guarded_human_step(**arguments)


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
