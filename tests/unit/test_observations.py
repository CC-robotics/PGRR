from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.observations import navigation_path_or_goal, select_local_path_waypoints
from ramp_core.types import Pose2D


def test_local_path_uses_untraversed_consecutive_suffix() -> None:
    path = tuple((float(x), 0.0) for x in range(11))
    waypoints = select_local_path_waypoints(path, Pose2D(8.0, 0.0, 0.0))

    np.testing.assert_allclose(waypoints[:, 0], [0.0, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    np.testing.assert_allclose(waypoints[:, 1], 0.0)
    assert not np.any(waypoints[:, 0] < 0.0)


def test_local_path_rotates_world_points_into_robot_frame() -> None:
    path = ((2.0, 3.0), (2.0, 4.0))
    waypoints = select_local_path_waypoints(path, Pose2D(2.0, 2.0, math.pi / 2.0))

    np.testing.assert_allclose(waypoints[0], [1.0, 0.0], atol=1.0e-6)
    np.testing.assert_allclose(waypoints[1], [2.0, 0.0], atol=1.0e-6)


def test_local_path_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_local_path_waypoints((), Pose2D(0.0, 0.0, 0.0))


def test_navigation_path_falls_back_to_original_goal() -> None:
    assert navigation_path_or_goal((), (4.0, -2.0)) == ((4.0, -2.0),)


def test_navigation_path_preserves_available_points() -> None:
    assert navigation_path_or_goal(((1.0, 2.0), (3.0, 4.0)), (9.0, 9.0)) == (
        (1.0, 2.0),
        (3.0, 4.0),
    )
