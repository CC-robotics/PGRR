from __future__ import annotations

import pytest
from ramp_core.recovery.safety import EmergencyEscapeController


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
    ) == (True, False)
    assert controller.update(
        now_s=1.4, hazard=True, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (True, False)
    assert controller.update(
        now_s=1.5, hazard=True, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (True, True)
    assert controller.update(
        now_s=2.2, hazard=False, linear_speed_mps=-0.15, rear_clearance_m=2.0
    ) == (True, True)
    assert controller.update(
        now_s=2.3, hazard=False, linear_speed_mps=0.0, rear_clearance_m=2.0
    ) == (False, False)


def test_emergency_never_backs_when_rear_clearance_is_unsafe() -> None:
    controller = _controller()
    controller.update(now_s=0.0, hazard=True, linear_speed_mps=0.0, rear_clearance_m=0.4)
    assert controller.update(
        now_s=5.0, hazard=True, linear_speed_mps=0.0, rear_clearance_m=0.4
    ) == (True, False)


def test_emergency_escape_configuration_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        EmergencyEscapeController(-0.1, 0.8, 0.7, 0.03)
