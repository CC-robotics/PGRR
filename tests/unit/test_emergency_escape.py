from __future__ import annotations

import math

import pytest
from ramp_core.recovery.safety import (
    EmergencyEscapeController,
    EmergencyEscapeMode,
    backup_increases_obstacle_clearance,
)


def _controller() -> EmergencyEscapeController:
    return EmergencyEscapeController(
        hold_s=0.5,
        backup_duration_s=0.8,
        backup_clearance_m=0.7,
        release_speed_mps=0.03,
    )


def test_emergency_stops_before_allowing_bounded_safe_backup() -> None:
    controller = _controller()
    assert controller.update(
        now_s=1.0, hazard=True, linear_speed_mps=0.2, rear_clearance_m=2.0
    ) == (True, EmergencyEscapeMode.STOP)
    assert controller.update(
        now_s=1.4, hazard=True, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (True, EmergencyEscapeMode.STOP)
    assert controller.update(
        now_s=1.5, hazard=True, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=2.2, hazard=False, linear_speed_mps=-0.15, rear_clearance_m=2.0
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=2.3, hazard=False, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (False, EmergencyEscapeMode.STOP)


def test_emergency_never_backs_when_rear_clearance_is_unsafe() -> None:
    controller = _controller()
    controller.update(now_s=0.0, hazard=True, linear_speed_mps=0.0, rear_clearance_m=0.4)
    assert controller.update(
        now_s=5.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.4,
        obstacle_clearance_m=0.3,
    ) == (True, EmergencyEscapeMode.STOP)


def test_footprint_hazard_cancels_active_backup() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=0.6,
        hazard=True,
        linear_speed_mps=-0.15,
        rear_clearance_m=2.0,
        backup_permitted=False,
        obstacle_clearance_m=0.3,
    ) == (True, EmergencyEscapeMode.STOP)


def test_unobserved_rear_uses_turn_then_observable_forward_escape() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)
    assert controller.update(
        now_s=1.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(120.0),
        obstacle_clearance_m=0.4,
        forward_clearance_m=1.0,
    ) == (True, EmergencyEscapeMode.FORWARD)


def test_backup_direction_guard_distinguishes_front_and_rear_obstacles() -> None:
    assert backup_increases_obstacle_clearance(math.radians(72.0))
    assert not backup_increases_obstacle_clearance(math.radians(123.0))


def test_emergency_escape_configuration_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        EmergencyEscapeController(-0.1, 0.8, 0.7, 0.03)
