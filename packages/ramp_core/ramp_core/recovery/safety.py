"""Deterministic emergency-stop release with a rear-clearance-constrained escape."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


def emergency_hazard_with_hysteresis(
    *,
    emergency_active: bool,
    motion_clearance_m: float,
    motion_stop_distance_m: float,
    footprint_clearance_m: float,
    footprint_stop_distance_m: float,
    release_hysteresis_m: float,
) -> bool:
    """Latch a geometric hazard until both clearances exceed release margins."""
    values = (
        motion_clearance_m,
        motion_stop_distance_m,
        footprint_clearance_m,
        footprint_stop_distance_m,
        release_hysteresis_m,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("emergency clearances and thresholds must be finite")
    if min(values) < 0.0:
        raise ValueError("emergency clearances and thresholds must be non-negative")
    hysteresis = release_hysteresis_m if emergency_active else 0.0
    return bool(
        motion_clearance_m < motion_stop_distance_m + hysteresis
        or footprint_clearance_m < footprint_stop_distance_m + hysteresis
    )


def update_collision_safety_latch(
    *,
    latched: bool,
    collision_risk: float,
    trigger_threshold: float,
    footprint_clearance_m: float,
    release_clearance_m: float,
) -> bool:
    """Retain collision-specific margins until measured clearance is restored."""
    values = (
        collision_risk,
        trigger_threshold,
        footprint_clearance_m,
        release_clearance_m,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("collision latch inputs must be finite")
    if not 0.0 <= collision_risk <= 1.0 or not 0.0 <= trigger_threshold <= 1.0:
        raise ValueError("collision probabilities and thresholds must lie in [0, 1]")
    if footprint_clearance_m < 0.0 or release_clearance_m < 0.0:
        raise ValueError("collision clearances must be non-negative")
    if collision_risk >= trigger_threshold:
        return True
    return bool(latched and footprint_clearance_m < release_clearance_m)


def backup_increases_obstacle_clearance(
    obstacle_angle_rad: float,
    *,
    maximum_forward_angle_rad: float = math.radians(80.0),
) -> bool:
    """Return whether reverse translation initially moves away from an obstacle."""
    if not math.isfinite(obstacle_angle_rad) or not 0.0 < maximum_forward_angle_rad <= math.pi:
        raise ValueError("obstacle angle must be finite and forward angle must lie in (0, pi]")
    wrapped = math.atan2(math.sin(obstacle_angle_rad), math.cos(obstacle_angle_rad))
    return abs(wrapped) <= maximum_forward_angle_rad


class EmergencyEscapeMode(str, Enum):
    STOP = "STOP"
    BACKUP = "BACKUP"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    FORWARD = "FORWARD"


def emergency_mode_reason(mode: EmergencyEscapeMode) -> str:
    """Return the stable telemetry label for an emergency escape mode."""
    return f"emergency_{mode.value.lower()}"


@dataclass
class EmergencyEscapeController:
    """Hold a stop, then choose a bounded observable geometric escape."""

    hold_s: float
    backup_duration_s: float
    backup_clearance_m: float
    release_speed_mps: float
    rotation_clearance_m: float = 0.30
    rear_obstacle_angle_rad: float = math.radians(100.0)
    forward_entry_clearance_m: float = 0.85
    backup_reset_clear_s: float = 3.0
    turn_reset_clear_s: float = 5.0
    maximum_improving_backups: int = 8
    backup_progress_m: float = 0.05
    hazard_since_s: float | None = None
    hazard_clear_since_s: float | None = None
    escape_until_s: float = float("-inf")
    mode: EmergencyEscapeMode = EmergencyEscapeMode.STOP
    backup_used_in_hazard: bool = False
    backup_count: int = 0
    backup_start_clearance_m: float | None = None
    backup_peak_clearance_m: float | None = None
    preferred_turn_mode: EmergencyEscapeMode | None = None

    def __post_init__(self) -> None:
        values = (
            self.hold_s,
            self.backup_duration_s,
            self.backup_clearance_m,
            self.release_speed_mps,
            self.rotation_clearance_m,
            self.forward_entry_clearance_m,
            self.backup_reset_clear_s,
            self.turn_reset_clear_s,
            self.backup_progress_m,
        )
        if any(value < 0.0 for value in values) or self.maximum_improving_backups <= 0:
            raise ValueError("emergency escape parameters must be non-negative")

    def update(
        self,
        *,
        now_s: float,
        hazard: bool,
        linear_speed_mps: float,
        rear_clearance_m: float,
        backup_permitted: bool = True,
        obstacle_angle_rad: float = 0.0,
        obstacle_clearance_m: float = math.inf,
        forward_clearance_m: float = math.inf,
        rear_observed: bool = True,
    ) -> tuple[bool, EmergencyEscapeMode]:
        """Return emergency state and a safety-directed maneuver mode."""

        # The robot still has to decelerate after a bounded reverse command
        # expires.  Preserve the best clearance actually observed during the
        # pulse; comparing only after stopping can erase a real improvement if
        # a dynamic obstacle keeps approaching during that deceleration.
        if (
            self.mode is EmergencyEscapeMode.BACKUP
            and self.backup_start_clearance_m is not None
            and math.isfinite(obstacle_clearance_m)
        ):
            self.backup_peak_clearance_m = max(
                self.backup_start_clearance_m,
                obstacle_clearance_m,
                self.backup_peak_clearance_m
                if self.backup_peak_clearance_m is not None
                else self.backup_start_clearance_m,
            )
        if now_s < self.escape_until_s:
            if self.mode is not EmergencyEscapeMode.BACKUP or backup_permitted:
                return True, self.mode
            self.escape_until_s = float("-inf")
            self.mode = EmergencyEscapeMode.STOP
        if not hazard:
            self.hazard_since_s = None
            self.mode = EmergencyEscapeMode.STOP
            if self.hazard_clear_since_s is None or now_s < self.hazard_clear_since_s:
                self.hazard_clear_since_s = now_s
            if now_s - self.hazard_clear_since_s >= self.backup_reset_clear_s:
                self.backup_used_in_hazard = False
                self.backup_count = 0
                self.backup_start_clearance_m = None
                self.backup_peak_clearance_m = None
            if now_s - self.hazard_clear_since_s >= self.turn_reset_clear_s:
                self.preferred_turn_mode = None
            return False, self.mode
        self.hazard_clear_since_s = None
        if self.hazard_since_s is None or now_s < self.hazard_since_s:
            self.hazard_since_s = now_s
        stopped = abs(linear_speed_mps) <= self.release_speed_mps
        held = now_s - self.hazard_since_s >= self.hold_s
        if not stopped or not held:
            self.mode = EmergencyEscapeMode.STOP
            return True, self.mode
        rear_safe = rear_observed and rear_clearance_m >= self.backup_clearance_m
        improving_repeat = (
            self.backup_start_clearance_m is not None
            and self.backup_peak_clearance_m is not None
            and self.backup_peak_clearance_m
            >= self.backup_start_clearance_m + self.backup_progress_m
            and self.backup_count < self.maximum_improving_backups
        )
        # A single reverse pulse is always bounded. Further pulses are allowed
        # only while each completed pulse measurably increases the nearest
        # observable clearance. This permits retreat from a bottleneck but
        # rejects the unchanged-clearance backup limit cycle.
        if backup_permitted and rear_safe and (not self.backup_used_in_hazard or improving_repeat):
            self.mode = EmergencyEscapeMode.BACKUP
            self.escape_until_s = now_s + self.backup_duration_s
            self.backup_used_in_hazard = True
            self.backup_count += 1
            self.backup_start_clearance_m = obstacle_clearance_m
            self.backup_peak_clearance_m = obstacle_clearance_m
            return True, self.mode
        wrapped = math.atan2(math.sin(obstacle_angle_rad), math.cos(obstacle_angle_rad))
        obstacle_is_rear = abs(wrapped) >= self.rear_obstacle_angle_rad
        if obstacle_is_rear and forward_clearance_m >= self.forward_entry_clearance_m:
            self.mode = EmergencyEscapeMode.FORWARD
            self.escape_until_s = now_s + self.backup_duration_s
            return True, self.mode
        if obstacle_clearance_m >= self.rotation_clearance_m:
            # Keep a safe turn direction through the +/-pi bearing wrap and
            # through nearest-obstacle identity changes. Re-choosing from the
            # instantaneous sign can produce an endless left/right limit
            # cycle before a separating forward heading is reached.
            if self.mode in {
                EmergencyEscapeMode.TURN_LEFT,
                EmergencyEscapeMode.TURN_RIGHT,
            }:
                return True, self.mode
            if self.preferred_turn_mode is None:
                self.preferred_turn_mode = (
                    EmergencyEscapeMode.TURN_RIGHT
                    if wrapped >= 0.0
                    else EmergencyEscapeMode.TURN_LEFT
                )
            self.mode = self.preferred_turn_mode
            return True, self.mode
        self.mode = EmergencyEscapeMode.STOP
        return True, self.mode
