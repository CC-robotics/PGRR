"""Deterministic emergency-stop release with a rear-clearance-constrained escape."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmergencyEscapeController:
    """Hold a stop, then permit a bounded backup only after the robot is still."""

    hold_s: float
    backup_duration_s: float
    backup_clearance_m: float
    release_speed_mps: float
    hazard_since_s: float | None = None
    escape_until_s: float = float("-inf")

    def __post_init__(self) -> None:
        values = (
            self.hold_s,
            self.backup_duration_s,
            self.backup_clearance_m,
            self.release_speed_mps,
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
    ) -> tuple[bool, bool]:
        """Return ``(emergency_active, safe_backup_active)``."""

        if not backup_permitted:
            self.escape_until_s = float("-inf")
            if not hazard:
                self.hazard_since_s = None
            elif self.hazard_since_s is None or now_s < self.hazard_since_s:
                self.hazard_since_s = now_s
            return hazard, False
        if now_s < self.escape_until_s:
            return True, True
        if not hazard:
            self.hazard_since_s = None
            return False, False
        if self.hazard_since_s is None or now_s < self.hazard_since_s:
            self.hazard_since_s = now_s
        stopped = abs(linear_speed_mps) <= self.release_speed_mps
        rear_safe = rear_clearance_m >= self.backup_clearance_m
        held = now_s - self.hazard_since_s >= self.hold_s
        if stopped and rear_safe and held:
            self.escape_until_s = now_s + self.backup_duration_s
            return True, True
        return True, False
