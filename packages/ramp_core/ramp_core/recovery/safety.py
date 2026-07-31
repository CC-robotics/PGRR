"""Deterministic emergency-stop release with a rear-clearance-constrained escape."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


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
    rotation_clearance_m: float = 0.36
    rear_obstacle_angle_rad: float = math.radians(100.0)
    hazard_since_s: float | None = None
    escape_until_s: float = float("-inf")
    mode: EmergencyEscapeMode = EmergencyEscapeMode.STOP

    def __post_init__(self) -> None:
        values = (
            self.hold_s,
            self.backup_duration_s,
            self.backup_clearance_m,
            self.release_speed_mps,
            self.rotation_clearance_m,
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
            return False, self.mode
        if self.hazard_since_s is None or now_s < self.hazard_since_s:
            self.hazard_since_s = now_s
        stopped = abs(linear_speed_mps) <= self.release_speed_mps
        held = now_s - self.hazard_since_s >= self.hold_s
        if not stopped or not held:
            self.mode = EmergencyEscapeMode.STOP
            return True, self.mode
        rear_safe = rear_observed and rear_clearance_m >= self.backup_clearance_m
        if backup_permitted and rear_safe:
            self.mode = EmergencyEscapeMode.BACKUP
            self.escape_until_s = now_s + self.backup_duration_s
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
