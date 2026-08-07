"""Deterministic emergency-stop release with a rear-clearance-constrained escape."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


def collision_latched_motion_clearance(
    *,
    configured_action_clearance_m: float,
    stop_clearance_m: float,
    release_hysteresis_m: float,
) -> float:
    """Keep every latched translation outside the latch-release boundary."""
    values = (
        configured_action_clearance_m,
        stop_clearance_m,
        release_hysteresis_m,
    )
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("collision-latched clearances must be finite and non-negative")
    return max(configured_action_clearance_m, stop_clearance_m + release_hysteresis_m)


def emergency_hazard_with_hysteresis(
    *,
    emergency_active: bool,
    motion_clearance_m: float,
    motion_stop_distance_m: float,
    footprint_clearance_m: float,
    footprint_stop_distance_m: float,
    release_hysteresis_m: float,
    footprint_release_hysteresis_m: float | None = None,
) -> bool:
    """Latch a geometric hazard until both clearances exceed release margins.

    The commanded-motion corridor and the omnidirectional footprint guard have
    different semantics.  A dynamic hazard benefits from release hysteresis in
    the direction of travel, while applying that same band to every LiDAR ray
    can make a harmless static side wall hold the robot forever after it has
    stopped.  Callers may therefore use a smaller footprint-only release band;
    omitting it preserves the historical shared-hysteresis behaviour.
    """
    footprint_hysteresis = (
        release_hysteresis_m
        if footprint_release_hysteresis_m is None
        else footprint_release_hysteresis_m
    )
    values = (
        motion_clearance_m,
        motion_stop_distance_m,
        footprint_clearance_m,
        footprint_stop_distance_m,
        release_hysteresis_m,
        footprint_hysteresis,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("emergency clearances and thresholds must be finite")
    if min(values) < 0.0:
        raise ValueError("emergency clearances and thresholds must be non-negative")
    motion_hysteresis = release_hysteresis_m if emergency_active else 0.0
    footprint_hysteresis = footprint_hysteresis if emergency_active else 0.0
    return bool(
        motion_clearance_m < motion_stop_distance_m + motion_hysteresis
        or footprint_clearance_m < footprint_stop_distance_m + footprint_hysteresis
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
    """Hold a stop, then choose a bounded observable geometric escape.

    Translation and rotation are finite pulses.  A turn direction is held
    only inside one pulse; every pulse boundary consumes a fresh observable
    clearance and bearing, and a persistent hazard has a finite turn budget.
    """

    hold_s: float
    backup_duration_s: float
    backup_clearance_m: float
    release_speed_mps: float
    rotation_clearance_m: float = 0.30
    turn_duration_s: float = 0.8
    maximum_turn_pulses: int = 4
    rear_obstacle_angle_rad: float = math.radians(80.0)
    forward_entry_clearance_m: float = 0.85
    backup_reset_clear_s: float = 3.0
    minimum_retreat_pulses: int = 3
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
    turn_count: int = 0
    progress_observed_after_hazard: bool = False
    turn_before_release: bool = False
    clear_turn_active: bool = False

    def __post_init__(self) -> None:
        values = (
            self.hold_s,
            self.backup_duration_s,
            self.backup_clearance_m,
            self.release_speed_mps,
            self.rotation_clearance_m,
            self.turn_duration_s,
            self.forward_entry_clearance_m,
            self.backup_reset_clear_s,
            self.backup_progress_m,
        )
        if (
            any(value < 0.0 for value in values)
            or self.turn_duration_s <= 0.0
            or self.maximum_turn_pulses <= 0
            or self.minimum_retreat_pulses <= 0
            or self.maximum_improving_backups <= 0
            or self.minimum_retreat_pulses > self.maximum_improving_backups
        ):
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
        goal_progress_observed: bool = False,
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
        turning = self.mode in {
            EmergencyEscapeMode.TURN_LEFT,
            EmergencyEscapeMode.TURN_RIGHT,
        }
        turn_active = turning and now_s < self.escape_until_s
        if turning:
            # Unlike a bounded reverse pulse, rotation should end immediately
            # when the hazard clears or when its omnidirectional swept margin
            # becomes unsafe.  An active safe pulse may still be preempted by
            # the higher-priority BACKUP/FORWARD checks below.
            if not hazard and not self.clear_turn_active:
                self.escape_until_s = float("-inf")
                self.mode = EmergencyEscapeMode.STOP
                turn_active = False
            elif obstacle_clearance_m < self.rotation_clearance_m:
                self.escape_until_s = float("-inf")
                self.mode = EmergencyEscapeMode.STOP
                self.clear_turn_active = False
                turn_active = False
            elif not turn_active:
                # Pulse expiry deliberately drops the sticky direction before
                # selecting again from the current observable bearing.
                self.escape_until_s = float("-inf")
                self.mode = EmergencyEscapeMode.STOP
                self.clear_turn_active = False

        if not turning and now_s < self.escape_until_s:
            if self.mode is not EmergencyEscapeMode.BACKUP or backup_permitted:
                return True, self.mode
            self.escape_until_s = float("-inf")
            self.mode = EmergencyEscapeMode.STOP
        if turn_active and self.clear_turn_active:
            return True, self.mode
        if not hazard and self.turn_before_release:
            # Recurrent hazards can clear during each individually safe BACKUP
            # pulse.  Releasing Nav2 immediately lets it undo that clearance
            # before the next decision, producing a forward/reverse limit
            # cycle.  After the configured retreat evidence has accumulated,
            # keep ownership for one bounded turn while the freshly observed
            # swept margin is still available.  The control loop continues to
            # enforce the same rotation-clearance boundary throughout.
            stopped = abs(linear_speed_mps) <= self.release_speed_mps
            if not stopped:
                self.mode = EmergencyEscapeMode.STOP
                return True, self.mode
            wrapped = math.atan2(math.sin(obstacle_angle_rad), math.cos(obstacle_angle_rad))
            if (
                obstacle_clearance_m >= self.rotation_clearance_m
                and self.turn_count < self.maximum_turn_pulses
            ):
                self.mode = (
                    EmergencyEscapeMode.TURN_RIGHT
                    if wrapped >= 0.0
                    else EmergencyEscapeMode.TURN_LEFT
                )
                self.escape_until_s = now_s + self.turn_duration_s
                self.turn_count += 1
                self.turn_before_release = False
                self.clear_turn_active = True
                return True, self.mode
            rear_safe = rear_observed and rear_clearance_m >= self.backup_clearance_m
            if (
                obstacle_clearance_m < self.rotation_clearance_m
                and backup_permitted
                and rear_safe
                and self.backup_count < self.maximum_improving_backups
            ):
                self.mode = EmergencyEscapeMode.BACKUP
                self.escape_until_s = now_s + self.backup_duration_s
                self.backup_used_in_hazard = True
                self.backup_count += 1
                self.backup_start_clearance_m = obstacle_clearance_m
                self.backup_peak_clearance_m = obstacle_clearance_m
                return True, self.mode
            self.mode = EmergencyEscapeMode.STOP
            return True, self.mode
        if not hazard:
            self.hazard_since_s = None
            self.mode = EmergencyEscapeMode.STOP
            if self.hazard_clear_since_s is None or now_s < self.hazard_clear_since_s:
                self.hazard_clear_since_s = now_s
            self.progress_observed_after_hazard |= goal_progress_observed
            # A short clear interval is not sufficient evidence of escape:
            # the nominal planner can briefly drive back into the same static
            # corner and otherwise renew the BACKUP/TURN budgets forever.  A
            # reset now requires both a stable clear interval and observable
            # progress toward the original task goal.  Retreat cannot create
            # this pulse because the caller's progress reference never moves
            # backward.
            if (
                now_s - self.hazard_clear_since_s >= self.backup_reset_clear_s
                and self.progress_observed_after_hazard
            ):
                self.backup_used_in_hazard = False
                self.backup_count = 0
                self.backup_start_clearance_m = None
                self.backup_peak_clearance_m = None
                self.turn_count = 0
                self.progress_observed_after_hazard = False
                self.turn_before_release = False
                self.clear_turn_active = False
            return False, self.mode
        self.hazard_clear_since_s = None
        if self.hazard_since_s is None or now_s < self.hazard_since_s:
            self.hazard_since_s = now_s
            self.progress_observed_after_hazard = False
        stopped = abs(linear_speed_mps) <= self.release_speed_mps
        held = now_s - self.hazard_since_s >= self.hold_s
        if not stopped or not held:
            self.mode = EmergencyEscapeMode.STOP
            return True, self.mode
        rear_safe = rear_observed and rear_clearance_m >= self.backup_clearance_m
        clearance_gain_m = float("-inf")
        if (
            self.backup_start_clearance_m is not None
            and self.backup_peak_clearance_m is not None
            and math.isfinite(self.backup_start_clearance_m)
            and math.isfinite(self.backup_peak_clearance_m)
        ):
            clearance_gain_m = self.backup_peak_clearance_m - self.backup_start_clearance_m
        improving_repeat = clearance_gain_m >= self.backup_progress_m
        clearance_creation_repeat = (
            0.0 < clearance_gain_m < self.backup_progress_m
            and self.backup_peak_clearance_m is not None
            and self.backup_peak_clearance_m < self.rotation_clearance_m
        )
        minimum_retreat_incomplete = self.backup_count < self.minimum_retreat_pulses
        # A short sequence of individually bounded pulses creates enough
        # separation to break a reciprocal head-on stop.  After that minimum,
        # every additional pulse requires measured clearance improvement.  A
        # smaller positive gain may create the swept clearance needed to turn,
        # but only while that clearance is still unavailable.  The existing
        # global pulse budget, independent rear observation, and caller-owned
        # planning/LiDAR gate remain authoritative for every pulse.
        if (
            backup_permitted
            and rear_safe
            and self.backup_count < self.maximum_improving_backups
            and (minimum_retreat_incomplete or improving_repeat or clearance_creation_repeat)
        ):
            self.mode = EmergencyEscapeMode.BACKUP
            self.escape_until_s = now_s + self.backup_duration_s
            self.backup_used_in_hazard = True
            self.backup_count += 1
            self.turn_before_release |= self.backup_count >= self.minimum_retreat_pulses
            self.backup_start_clearance_m = obstacle_clearance_m
            self.backup_peak_clearance_m = obstacle_clearance_m
            return True, self.mode
        wrapped = math.atan2(math.sin(obstacle_angle_rad), math.cos(obstacle_angle_rad))
        obstacle_is_rear = abs(wrapped) >= self.rear_obstacle_angle_rad
        if obstacle_is_rear and forward_clearance_m >= self.forward_entry_clearance_m:
            self.mode = EmergencyEscapeMode.FORWARD
            self.escape_until_s = now_s + self.backup_duration_s
            return True, self.mode
        if turn_active:
            return True, self.mode
        if (
            obstacle_clearance_m >= self.rotation_clearance_m
            and self.turn_count < self.maximum_turn_pulses
        ):
            self.mode = (
                EmergencyEscapeMode.TURN_RIGHT if wrapped >= 0.0 else EmergencyEscapeMode.TURN_LEFT
            )
            self.escape_until_s = now_s + self.turn_duration_s
            self.turn_count += 1
            self.turn_before_release = False
            return True, self.mode
        self.mode = EmergencyEscapeMode.STOP
        return True, self.mode
