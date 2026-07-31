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


@dataclass
class EmergencyEscapeController:
    """Hold a stop, then choose a bounded observable geometric escape."""

    hold_s: float
    backup_duration_s: float
    backup_clearance_m: float
    release_speed_mps: float
    rotation_clearance_m: float = 0.30
    rear_obstacle_angle_rad: float = math.radians(100.0)
    backup_reset_clear_s: float = 3.0
    hazard_since_s: float | None = None
    hazard_clear_since_s: float | None = None
    escape_until_s: float = float("-inf")
    mode: EmergencyEscapeMode = EmergencyEscapeMode.STOP
    backup_used_in_hazard: bool = False

    def __post_init__(self) -> None:
        values = (
            self.hold_s,
            self.backup_duration_s,
            self.backup_clearance_m,
            self.release_speed_mps,
            self.rotation_clearance_m,
            self.backup_reset_clear_s,
        )
        if any(value < 0.0 for value in values):
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
        # Repeating short reverse pulses can create a limit cycle beside an
        # obstacle: each pulse clears the immediate footprint test without
        # escaping the continuous hazard. Permit only one reverse option per
        # hazard interval, then require a turn/forward geometric escape.
        if backup_permitted and rear_safe and not self.backup_used_in_hazard:
            self.mode = EmergencyEscapeMode.BACKUP
            self.escape_until_s = now_s + self.backup_duration_s
            self.backup_used_in_hazard = True
            return True, self.mode
        wrapped = math.atan2(math.sin(obstacle_angle_rad), math.cos(obstacle_angle_rad))
        obstacle_is_rear = abs(wrapped) >= self.rear_obstacle_angle_rad
        if obstacle_is_rear and forward_clearance_m >= self.backup_clearance_m:
            self.mode = EmergencyEscapeMode.FORWARD
            self.escape_until_s = now_s + self.backup_duration_s
            return True, self.mode
        if obstacle_clearance_m >= self.rotation_clearance_m:
            self.mode = (
                EmergencyEscapeMode.TURN_RIGHT if wrapped >= 0.0 else EmergencyEscapeMode.TURN_LEFT
            )
            return True, self.mode
        self.mode = EmergencyEscapeMode.STOP
        return True, self.mode
