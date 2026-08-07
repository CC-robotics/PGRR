import pytest
from ramp_core.planning.pure_pursuit import pure_pursuit_command
from ramp_core.types import Pose2D


def test_pure_pursuit_drives_straight_path() -> None:
    command = pure_pursuit_command(Pose2D(0.0, 0.0, 0.0), [(0.5, 0.0), (1.0, 0.0)])
    assert command.linear > 0.0
    assert command.angular == pytest.approx(0.0)


def test_pure_pursuit_stops_for_empty_path() -> None:
    command = pure_pursuit_command(Pose2D(0.0, 0.0, 0.0), [])
    assert (command.linear, command.angular) == (0.0, 0.0)
