import math

import pytest
from ramp_core.geometry import normalize_angle, robot_to_world, world_to_robot
from ramp_core.types import Pose2D


def test_coordinate_transforms_round_trip() -> None:
    robot = Pose2D(2.0, -1.0, math.pi / 3.0)
    local = (0.7, -0.2)
    world = robot_to_world(local, robot)
    assert world_to_robot(world, robot) == pytest.approx(local)


def test_normalize_angle_half_open_interval() -> None:
    assert normalize_angle(math.pi) == pytest.approx(-math.pi)
    assert normalize_angle(3.0 * math.pi) == pytest.approx(-math.pi)
