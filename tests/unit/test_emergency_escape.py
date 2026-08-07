from __future__ import annotations

import math

import pytest
from ramp_core.recovery.safety import (
    EmergencyEscapeController,
    EmergencyEscapeMode,
    backup_increases_obstacle_clearance,
    collision_latched_motion_clearance,
    emergency_hazard_with_hysteresis,
    emergency_mode_reason,
    update_collision_safety_latch,
)


def test_collision_latched_motion_cannot_enter_unreleasable_clearance_band() -> None:
    assert collision_latched_motion_clearance(
        configured_action_clearance_m=0.65,
        stop_clearance_m=0.85,
        release_hysteresis_m=0.05,
    ) == pytest.approx(0.90)
    assert collision_latched_motion_clearance(
        configured_action_clearance_m=1.0,
        stop_clearance_m=0.85,
        release_hysteresis_m=0.05,
    ) == pytest.approx(1.0)


def _controller(
    *,
    minimum_retreat_pulses: int = 3,
    rotation_clearance_m: float = 0.30,
    turn_duration_s: float = 0.8,
    maximum_turn_pulses: int = 4,
) -> EmergencyEscapeController:
    return EmergencyEscapeController(
        hold_s=0.5,
        backup_duration_s=0.8,
        backup_clearance_m=0.7,
        release_speed_mps=0.03,
        rotation_clearance_m=rotation_clearance_m,
        turn_duration_s=turn_duration_s,
        maximum_turn_pulses=maximum_turn_pulses,
        minimum_retreat_pulses=minimum_retreat_pulses,
    )


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (EmergencyEscapeMode.STOP, "emergency_stop"),
        (EmergencyEscapeMode.BACKUP, "emergency_backup"),
        (EmergencyEscapeMode.TURN_LEFT, "emergency_turn_left"),
        (EmergencyEscapeMode.TURN_RIGHT, "emergency_turn_right"),
        (EmergencyEscapeMode.FORWARD, "emergency_forward"),
    ],
)
def test_emergency_mode_has_stable_telemetry(mode: EmergencyEscapeMode, reason: str) -> None:
    assert emergency_mode_reason(mode) == reason


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


def test_footprint_release_hysteresis_can_be_separated_from_motion_hysteresis() -> None:
    values = {
        "motion_clearance_m": 2.0,
        "motion_stop_distance_m": 0.85,
        "footprint_clearance_m": 0.49,
        "footprint_stop_distance_m": 0.48,
        "release_hysteresis_m": 0.05,
    }
    assert emergency_hazard_with_hysteresis(emergency_active=True, **values)
    assert not emergency_hazard_with_hysteresis(
        emergency_active=True,
        footprint_release_hysteresis_m=0.0,
        **values,
    )


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
    controller = _controller(minimum_retreat_pulses=1)
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
        goal_progress_observed=True,
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


def test_emergency_forward_rejects_clearance_below_strict_entry_margin() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(120.0),
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(120.0),
        obstacle_clearance_m=0.4,
        forward_clearance_m=0.8,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)


def test_forward_escape_starts_only_after_obstacle_crosses_transverse_plane() -> None:
    controller = _controller()
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(89.0),
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(89.0),
        obstacle_clearance_m=0.4,
        forward_clearance_m=1.0,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_angle_rad=math.radians(91.0),
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


def test_emergency_turn_stops_when_observable_clearance_falls_below_margin() -> None:
    controller = _controller(rotation_clearance_m=0.53)
    common = {
        "hazard": True,
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 0.0,
        "rear_observed": False,
        "obstacle_angle_rad": -0.4,
    }
    assert controller.update(now_s=0.0, obstacle_clearance_m=0.60, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=0.5, obstacle_clearance_m=0.60, **common) == (
        True,
        EmergencyEscapeMode.TURN_LEFT,
    )
    # The active pulse is cancelled immediately instead of persisting to its
    # nominal 1.3 s expiry after the observable footprint margin becomes unsafe.
    assert controller.update(now_s=0.6, obstacle_clearance_m=0.52, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )


def test_turn_pulses_recheck_direction_and_have_a_persistent_hazard_limit() -> None:
    controller = _controller(maximum_turn_pulses=2)
    common = {
        "hazard": True,
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 0.0,
        "rear_observed": False,
        "obstacle_clearance_m": 0.60,
    }
    assert controller.update(now_s=0.0, obstacle_angle_rad=0.4, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=0.5, obstacle_angle_rad=0.4, **common) == (
        True,
        EmergencyEscapeMode.TURN_RIGHT,
    )
    # Bearing changes do not chatter inside a pulse.
    assert controller.update(now_s=1.0, obstacle_angle_rad=-0.4, **common) == (
        True,
        EmergencyEscapeMode.TURN_RIGHT,
    )
    # Once the pulse expires, the current bearing selects the next direction.
    assert controller.update(now_s=1.31, obstacle_angle_rad=-0.4, **common) == (
        True,
        EmergencyEscapeMode.TURN_LEFT,
    )
    # A persistent hazard cannot renew rotation after the finite pulse budget.
    assert controller.update(now_s=2.12, obstacle_angle_rad=-0.4, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=10.0, obstacle_angle_rad=-0.4, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.turn_count == 2

    assert controller.update(
        now_s=10.1,
        hazard=False,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_clearance_m=0.60,
    ) == (False, EmergencyEscapeMode.STOP)
    assert controller.turn_count == 2
    assert controller.update(
        now_s=13.1,
        hazard=False,
        linear_speed_mps=0.0,
        rear_clearance_m=0.0,
        rear_observed=False,
        obstacle_clearance_m=0.60,
        goal_progress_observed=True,
    ) == (False, EmergencyEscapeMode.STOP)
    assert controller.turn_count == 0


def test_clear_time_without_goal_progress_does_not_reset_escape_budgets() -> None:
    controller = _controller(minimum_retreat_pulses=2)
    common = {
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 2.0,
        "obstacle_angle_rad": 0.2,
        "obstacle_clearance_m": 0.4,
    }
    assert controller.update(now_s=0.0, hazard=True, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=0.5, hazard=True, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.update(now_s=1.4, hazard=False, **common) == (
        False,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=5.0, hazard=False, **common) == (
        False,
        EmergencyEscapeMode.STOP,
    )
    assert controller.backup_count == 1
    assert controller.update(now_s=5.1, hazard=True, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=5.6, hazard=True, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.backup_count == 2


def test_recurrent_retreat_turns_before_nominal_motion_can_undo_clearance() -> None:
    controller = _controller(minimum_retreat_pulses=3, rotation_clearance_m=0.40)
    common = {
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 2.0,
        "obstacle_angle_rad": 0.2,
    }
    assert controller.update(now_s=0.0, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=0.5, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.update(now_s=1.4, hazard=False, obstacle_clearance_m=0.54, **common) == (
        False,
        EmergencyEscapeMode.STOP,
    )

    assert controller.update(now_s=1.5, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=2.0, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.update(now_s=2.9, hazard=False, obstacle_clearance_m=0.54, **common) == (
        False,
        EmergencyEscapeMode.STOP,
    )

    assert controller.update(now_s=3.0, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=3.5, hazard=True, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    # The third independently rear-gated retreat creates a safe 0.54 m swept
    # margin.  Keep recovery ownership and turn before Nav2 can drive forward
    # into the same 0.42 m corner again.
    assert controller.update(now_s=4.4, hazard=False, obstacle_clearance_m=0.54, **common) == (
        True,
        EmergencyEscapeMode.TURN_RIGHT,
    )
    assert controller.update(now_s=4.8, hazard=False, obstacle_clearance_m=0.50, **common) == (
        True,
        EmergencyEscapeMode.TURN_RIGHT,
    )
    assert controller.update(now_s=5.3, hazard=False, obstacle_clearance_m=0.48, **common) == (
        False,
        EmergencyEscapeMode.STOP,
    )


def test_continuous_hazard_can_repeat_only_when_backup_improves_clearance() -> None:
    controller = _controller(minimum_retreat_pulses=1)
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.46,
    ) == (True, EmergencyEscapeMode.BACKUP)


def test_positive_subthreshold_gain_can_create_missing_rotation_clearance() -> None:
    controller = _controller(minimum_retreat_pulses=1, rotation_clearance_m=0.53)
    common = {
        "hazard": True,
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 2.0,
        "obstacle_angle_rad": 0.2,
    }
    assert controller.update(now_s=0.0, obstacle_clearance_m=0.45, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.update(now_s=0.5, obstacle_clearance_m=0.45, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    # The 0.041 m gain is real but below the ordinary 0.05 m repeat threshold.
    # Because rotation is still unsafe, one more independently gated pulse can
    # continue creating clearance instead of entering an unrecoverable stop.
    assert controller.update(now_s=1.4, obstacle_clearance_m=0.491, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )


@pytest.mark.parametrize(
    ("rear_clearance_m", "backup_permitted"),
    [(0.69, True), (2.0, False)],
)
def test_clearance_creation_repeat_never_bypasses_translation_gates(
    rear_clearance_m: float,
    backup_permitted: bool,
) -> None:
    controller = _controller(minimum_retreat_pulses=1, rotation_clearance_m=0.53)
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.45,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.45,
    ) == (True, EmergencyEscapeMode.BACKUP)
    # A positive 0.041 m gain cannot override either the independently
    # observed rear margin or the caller's planning/LiDAR/net-retreat gate.
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=rear_clearance_m,
        backup_permitted=backup_permitted,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.491,
    ) == (True, EmergencyEscapeMode.STOP)


def test_subthreshold_clearance_creation_still_obeys_hard_pulse_limit() -> None:
    controller = EmergencyEscapeController(
        hold_s=0.0,
        backup_duration_s=0.1,
        backup_clearance_m=0.7,
        release_speed_mps=0.03,
        rotation_clearance_m=0.53,
        minimum_retreat_pulses=1,
        maximum_improving_backups=2,
        backup_progress_m=0.05,
    )
    common = {
        "hazard": True,
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 2.0,
        "obstacle_angle_rad": 0.2,
    }
    assert controller.update(now_s=0.0, obstacle_clearance_m=0.40, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.update(now_s=0.2, obstacle_clearance_m=0.42, **common) == (
        True,
        EmergencyEscapeMode.BACKUP,
    )
    assert controller.update(now_s=0.4, obstacle_clearance_m=0.44, **common) == (
        True,
        EmergencyEscapeMode.STOP,
    )
    assert controller.backup_count == 2


def test_minimum_retreat_uses_three_rear_safe_pulses_before_requiring_gain() -> None:
    controller = _controller(minimum_retreat_pulses=3)
    common = {
        "hazard": True,
        "linear_speed_mps": 0.0,
        "rear_clearance_m": 2.0,
        "backup_permitted": True,
        "obstacle_angle_rad": 0.2,
        "obstacle_clearance_m": 0.4,
    }
    assert controller.update(now_s=0.0, **common) == (True, EmergencyEscapeMode.STOP)
    assert controller.update(now_s=0.5, **common) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(now_s=1.4, **common) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(now_s=2.3, **common) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(now_s=3.2, **common) == (True, EmergencyEscapeMode.TURN_RIGHT)
    assert controller.backup_count == 3


def test_minimum_retreat_never_bypasses_rear_or_footprint_guards() -> None:
    controller = _controller(minimum_retreat_pulses=3)
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=0.6,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)

    controller = _controller(minimum_retreat_pulses=3)
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        backup_permitted=False,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.TURN_RIGHT)


def test_backup_peak_survives_deceleration_before_repeat_decision() -> None:
    controller = _controller(minimum_retreat_pulses=1)
    controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.45,
    )
    assert controller.update(
        now_s=0.5,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.45,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=1.2,
        hazard=True,
        linear_speed_mps=-0.15,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.52,
    ) == (True, EmergencyEscapeMode.BACKUP)
    # The command has expired, but the robot has not stopped.  A closing
    # obstacle reduces instantaneous clearance during deceleration.
    assert controller.update(
        now_s=1.4,
        hazard=True,
        linear_speed_mps=-0.10,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.48,
    ) == (True, EmergencyEscapeMode.STOP)
    # Once stopped, the controller uses the measured pulse peak (0.52 m), not
    # the later 0.48 m value, to authorize one more bounded reverse pulse.
    assert controller.update(
        now_s=1.6,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.47,
    ) == (True, EmergencyEscapeMode.BACKUP)


def test_improving_backup_sequence_has_a_hard_limit() -> None:
    controller = EmergencyEscapeController(
        hold_s=0.0,
        backup_duration_s=0.1,
        backup_clearance_m=0.7,
        release_speed_mps=0.03,
        minimum_retreat_pulses=1,
        maximum_improving_backups=2,
        backup_progress_m=0.05,
    )
    assert controller.update(
        now_s=0.0,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.4,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=0.2,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_clearance_m=0.5,
    ) == (True, EmergencyEscapeMode.BACKUP)
    assert controller.update(
        now_s=0.4,
        hazard=True,
        linear_speed_mps=0.0,
        rear_clearance_m=2.0,
        obstacle_angle_rad=0.2,
        obstacle_clearance_m=0.6,
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
    with pytest.raises(ValueError, match="non-negative"):
        _controller(turn_duration_s=0.0)
    with pytest.raises(ValueError, match="non-negative"):
        _controller(maximum_turn_pulses=0)
