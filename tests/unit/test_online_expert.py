from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.online import augment_grid_with_scan, estimate_human_states
from ramp_core.types import Pose2D


def test_human_velocity_estimation_is_index_stable() -> None:
    states = estimate_human_states(
        ((1.0, 0.0), (0.0, 2.0)),
        ((0.5, 0.0), (0.0, 1.5)),
        0.5,
    )
    assert states[0].velocity == pytest.approx((1.0, 0.0))
    assert states[1].velocity == pytest.approx((0.0, 1.0))


def test_human_velocity_estimation_caps_discontinuity() -> None:
    state = estimate_human_states(((10.0, 0.0),), ((0.0, 0.0),), 0.1)[0]
    assert math.hypot(*state.velocity) == pytest.approx(2.0)


def test_scan_endpoints_are_added_without_mutating_static_grid() -> None:
    static = OccupancyGrid(np.zeros((30, 30), dtype=np.bool_), 0.1)
    augmented = augment_grid_with_scan(
        static,
        Pose2D(1.0, 1.0, 0.0),
        [1.0],
        angle_min=0.0,
        angle_increment=0.1,
        minimum_range_m=0.05,
        maximum_range_m=5.0,
        inflation_m=0.2,
    )
    endpoint = augmented.world_to_grid(2.0, 1.0)
    assert not bool(static.occupied[endpoint])
    assert bool(augmented.occupied[endpoint])
    assert bool(augmented.occupied[endpoint[0] + 1, endpoint[1]])


def test_scan_ignores_max_range_returns() -> None:
    static = OccupancyGrid(np.zeros((30, 30), dtype=np.bool_), 0.1)
    augmented = augment_grid_with_scan(
        static,
        Pose2D(1.0, 1.0, 0.0),
        [5.0],
        angle_min=0.0,
        angle_increment=0.1,
        minimum_range_m=0.05,
        maximum_range_m=5.0,
    )
    assert not bool(augmented.occupied.any())
