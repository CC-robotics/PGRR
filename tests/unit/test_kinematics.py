import math

import pytest
from ramp_core.kinematics import integrate_differential_drive, stopping_distance
from ramp_core.types import Pose2D, Velocity2D


def test_straight_differential_drive_step() -> None:
    pose = integrate_differential_drive(Pose2D(0.0, 0.0, 0.0), Velocity2D(1.0, 0.0), 0.5)
    assert (pose.x, pose.y, pose.yaw) == pytest.approx((0.5, 0.0, 0.0))


def test_curved_differential_drive_step() -> None:
    pose = integrate_differential_drive(Pose2D(0.0, 0.0, 0.0), Velocity2D(1.0, math.pi / 2.0), 1.0)
    radius = 2.0 / math.pi
    assert (pose.x, pose.y, pose.yaw) == pytest.approx((radius, radius, math.pi / 2.0))


def test_stopping_distance_includes_latency_and_margin() -> None:
    assert stopping_distance(1.0, 2.0, 0.1, 0.2) == pytest.approx(0.55)
