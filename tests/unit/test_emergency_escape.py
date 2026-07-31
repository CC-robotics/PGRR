from __future__ import annotations

import math

import pytest
from ramp_core.recovery.safety import (
    EmergencyEscapeController,
    EmergencyEscapeMode,
    backup_increases_obstacle_clearance,
    emergency_hazard_with_hysteresis,
    update_collision_safety_latch,
)


def _controller() -> EmergencyEscapeController:
    return EmergencyEscapeController(
        hold_s=0.5,
        backup_duration_s=0.8,
        backup_clearance_m=0.7,
        release_speed_mps=0.03,
    )


def test_emergency_hazard_uses_a_stricter_release_clearance() -> None:
    values = {
        "motion_clearance_m": 2.0,
        "motion_stop_distance_m": 0.45,
        "footprint_clearance_m": 0.87,
        "footprint_stop_distance_m": 0.85,
        "release_hysteresis_m": 0.05,
    }
    assert not emergency_hazard_with_hysteresis(emergency_active=False, **values)
    assert emergency_hazard_with_hysteresis(emergency_active=True, **values)
    values["footprint_clearance_m"] = 0.91
    assert not emergency_hazard_with_hysteresis(emergency_active=True, **values)


def test_emergency_hazard_rejects_negative_hysteresis() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        emergency_hazard_with_hysteresis(
            emergency_active=True,
            motion_clearance_m=1.0,
            motion_stop_distance_m=0.5,
            footprint_clearance_m=1.0,
            footprint_stop_distance_m=0.5,
            release_hysteresis_m=-0.1,
        )


def test_collision_margin_latch_survives_a_single_cleared_prediction() -> None:
    assert update_collision_safety_latch(
        latched=False,
        collision_risk=0.75,
        trigger_threshold=0.65,
        footprint_clearance_m=0.60,
        release_clearance_m=0.90,
    )
    assert update_collision_safety_latch(
        latched=True,
        collision_risk=0.0,
        trigger_threshold=0.65,
        footprint_clearance_m=0.89,
        release_clearance_m=0.90,
    )
    assert not update_collision_safety_latch(
        latched=True,
        collision_risk=0.0,
        trigger_threshold=0.65,
        footprint_clearance_m=0.91,
        release_clearance_m=0.90,
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


def test_emergency_uses_rotation_instead_of_backing_when_rear_is_unsafe() -> None:
    controller = _controller()
    controller.update(now_s=0.0, hazard=True, linear_speed_mps=0.0, rear_clearance_m=0.4)
    assert controller.update(
        now_s=5.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.4,
        obstacle_clearance_m=0.3,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)


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


def test_continuous_hazard_cannot_repeat_backup_limit_cycle() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)
    controller.update(
        now_s=2.0,
        hazard=False,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
    )
    assert controller.update(
        now_s=2.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.STOP)
    assert controller.update(
        now_s=3.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)

    controller.update(
        now_s=4.0,
        hazard=False,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
    )
    controller.update(
        now_s=7.0,
        hazard=False,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
    )
    assert controller.update(
        now_s=7.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.STOP)
    assert controller.update(
        now_s=8.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)


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


def test_emergency_turn_direction_persists_across_bearing_sign_change() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=0.4,
        obstacle_clearance_m=0.8,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=0.4,
        obstacle_clearance_m=0.8,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)
    assert controller.update(
        now_s=0.6,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=-0.4,
        obstacle_clearance_m=0.8,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)


def test_narrow_door_rotation_uses_inscribed_clearance_not_circumscribed_radius() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=-0.4,
        obstacle_clearance_m=0.31,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=-0.4,
        obstacle_clearance_m=0.31,
    ) == (True, EmergencyEscapeMode.TURN_LEFT)


def test_backup_direction_guard_distinguishes_front_and_rear_obstacles() -> None:
    assert backup_increases_obstacle_clearance(math.radians(72.0))
    assert not backup_increases_obstacle_clearance(math.radians(123.0))


def test_emergency_escape_configuration_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        EmergencyEscapeController(-0.1, 0.8, 0.7, 0.03)
