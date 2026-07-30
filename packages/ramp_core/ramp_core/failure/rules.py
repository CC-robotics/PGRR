"""Observable-only rule detector for collision risk, freeze, oscillation, and deadlock."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from ramp_core.failure.metrics import angular_sign_changes, goal_progress, path_displacement
from ramp_core.kinematics import stopping_distance
from ramp_core.types import FailurePrediction, PlannerStatus


@dataclass(frozen=True, slots=True)
class RuleFailureConfig:
    braking_acceleration: float = 1.2
    control_latency_s: float = 0.20
    safety_margin_m: float = 0.25
    ttc_threshold_s: float = 1.5
    collision_absolute_distance_m: float = 0.9
    collision_wide_absolute_distance_m: float = 0.7
    collision_release_distance_m: float = 1.2
    collision_hold_s: float = 2.0
    collision_proximity_m: float = 1.50
    collision_closing_speed_mps: float = 0.10
    collision_radial_excess_closing_speed_mps: float = 0.25
    collision_proximity_score: float = 0.75
    collision_trend_window_s: float = 0.5
    collision_max_angular_speed_radps: float = 0.30
    freeze_window_s: float = 3.0
    freeze_goal_distance_m: float = 1.0
    freeze_displacement_m: float = 0.15
    requested_motion_speed_mps: float = 0.05
    requested_motion_fraction: float = 0.50
    oscillation_window_s: float = 4.0
    oscillation_sign_changes: int = 6
    oscillation_progress_m: float = 0.20
    angular_deadband_radps: float = 0.08
    deadlock_window_s: float = 4.0
    deadlock_obstacle_distance_m: float = 1.2
    deadlock_displacement_m: float = 0.15
    deadlock_speed_mps: float = 0.08

    def __post_init__(self) -> None:
        positive = (
            self.braking_acceleration,
            self.ttc_threshold_s,
            self.collision_absolute_distance_m,
            self.collision_wide_absolute_distance_m,
            self.collision_release_distance_m,
            self.collision_proximity_m,
            self.collision_trend_window_s,
            self.freeze_window_s,
            self.freeze_goal_distance_m,
            self.oscillation_window_s,
            self.deadlock_window_s,
            self.deadlock_obstacle_distance_m,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("positive failure-rule parameters must be greater than zero")
        nonnegative = (
            self.control_latency_s,
            self.safety_margin_m,
            self.collision_hold_s,
            self.collision_closing_speed_mps,
            self.collision_radial_excess_closing_speed_mps,
            self.collision_max_angular_speed_radps,
            self.freeze_displacement_m,
            self.requested_motion_speed_mps,
            self.oscillation_progress_m,
            self.angular_deadband_radps,
            self.deadlock_displacement_m,
            self.deadlock_speed_mps,
        )
        if any(value < 0.0 for value in nonnegative):
            raise ValueError("failure-rule distances, speeds, and margins must be non-negative")
        if self.oscillation_sign_changes <= 0:
            raise ValueError("oscillation_sign_changes must be positive")
        if not 0.0 <= self.collision_proximity_score <= 1.0:
            raise ValueError("collision_proximity_score must lie in [0, 1]")
        if not 0.0 <= self.requested_motion_fraction <= 1.0:
            raise ValueError("requested_motion_fraction must lie in [0, 1]")
        if self.collision_release_distance_m <= self.collision_wide_absolute_distance_m:
            raise ValueError(
                "collision_release_distance_m must exceed collision_wide_absolute_distance_m"
            )


@dataclass(frozen=True, slots=True)
class TimedNavigationSample:
    timestamp: float
    position: tuple[float, float]
    goal_distance: float
    linear_velocity: float
    angular_velocity: float
    base_linear_command: float
    base_angular_command: float
    nearest_lidar_distance: float
    planner_status: PlannerStatus = PlannerStatus.UNKNOWN
    goal_reached: bool = False
    forward_lidar_distance: float | None = None
    collision_lidar_distance: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.timestamp,
            *self.position,
            self.goal_distance,
            self.linear_velocity,
            self.angular_velocity,
            self.base_linear_command,
            self.base_angular_command,
            self.nearest_lidar_distance,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("navigation sample values must be finite")
        if self.timestamp < 0.0 or self.goal_distance < 0.0 or self.nearest_lidar_distance < 0.0:
            raise ValueError("timestamp and distances must be non-negative")
        if self.forward_lidar_distance is not None and (
            not math.isfinite(self.forward_lidar_distance) or self.forward_lidar_distance < 0.0
        ):
            raise ValueError("forward_lidar_distance must be finite and non-negative")
        if self.collision_lidar_distance is not None and (
            not math.isfinite(self.collision_lidar_distance) or self.collision_lidar_distance < 0.0
        ):
            raise ValueError("collision_lidar_distance must be finite and non-negative")


class RuleFailureDetector:
    def __init__(self, config: RuleFailureConfig | None = None) -> None:
        self.config = config if config is not None else RuleFailureConfig()
        horizon = max(
            self.config.freeze_window_s,
            self.config.oscillation_window_s,
            self.config.deadlock_window_s,
        )
        self._history: deque[TimedNavigationSample] = deque()
        self._horizon_s = horizon
        self._last_collision_risk_timestamp: float | None = None

    def reset(self) -> None:
        self._history.clear()
        self._last_collision_risk_timestamp = None

    def _window(self, duration: float) -> list[TimedNavigationSample]:
        if not self._history:
            return []
        threshold = self._history[-1].timestamp - duration
        return [sample for sample in self._history if sample.timestamp >= threshold]

    @staticmethod
    def _covers(window: list[TimedNavigationSample], duration: float) -> bool:
        return len(window) >= 2 and window[-1].timestamp - window[0].timestamp >= duration * 0.95

    def update(self, sample: TimedNavigationSample) -> FailurePrediction:
        if self._history and sample.timestamp < self._history[-1].timestamp:
            raise ValueError("sample timestamps must be monotonic")
        self._history.append(sample)
        cutoff = sample.timestamp - self._horizon_s - 0.5
        while len(self._history) > 1 and self._history[1].timestamp < cutoff:
            self._history.popleft()

        forward_clearance = (
            sample.forward_lidar_distance
            if sample.forward_lidar_distance is not None
            else sample.nearest_lidar_distance
        )
        collision_clearance = (
            sample.collision_lidar_distance
            if sample.collision_lidar_distance is not None
            else forward_clearance
        )
        stop_distance = stopping_distance(
            sample.linear_velocity,
            self.config.braking_acceleration,
            self.config.control_latency_s,
            self.config.safety_margin_m,
        )
        collision = 1.0 if forward_clearance <= stop_distance else 0.0
        # A fixed corridor wall can remain close to the robot's side for an
        # entire episode. Apply the absolute threshold to the forward sector;
        # omnidirectional hazards are handled by their closing trend below.
        if forward_clearance <= self.config.collision_absolute_distance_m:
            collision = 1.0
        # The narrow forward sector avoids classifying corridor side walls as
        # hazards, but a crossing person can leave that sector while remaining
        # in the robot's swept near field. Use a smaller absolute threshold in
        # the wider collision sector to cover that observable case.
        if collision_clearance <= self.config.collision_wide_absolute_distance_m:
            collision = 1.0
        forward_speed = max(0.0, sample.linear_velocity)
        if forward_speed > 1.0e-3:
            ttc = max(0.0, forward_clearance - self.config.safety_margin_m) / forward_speed
            if ttc <= self.config.ttc_threshold_s:
                collision = max(collision, 1.0 - 0.5 * ttc / self.config.ttc_threshold_s)
        collision_window = self._window(self.config.collision_trend_window_s)
        if self._covers(collision_window, self.config.collision_trend_window_s):
            duration = collision_window[-1].timestamp - collision_window[0].timestamp
            first_collision_clearance = (
                collision_window[0].collision_lidar_distance
                if collision_window[0].collision_lidar_distance is not None
                else (
                    collision_window[0].forward_lidar_distance
                    if collision_window[0].forward_lidar_distance is not None
                    else collision_window[0].nearest_lidar_distance
                )
            )
            last_collision_clearance = (
                collision_window[-1].collision_lidar_distance
                if collision_window[-1].collision_lidar_distance is not None
                else (
                    collision_window[-1].forward_lidar_distance
                    if collision_window[-1].forward_lidar_distance is not None
                    else collision_window[-1].nearest_lidar_distance
                )
            )
            closing_speed = (first_collision_clearance - last_collision_clearance) / max(
                duration, 1.0e-6
            )
            radial_closing_speed = (
                collision_window[0].nearest_lidar_distance
                - collision_window[-1].nearest_lidar_distance
            ) / max(duration, 1.0e-6)
            if (
                collision_clearance <= self.config.collision_proximity_m
                and closing_speed
                >= abs(sample.linear_velocity)
                + self.config.collision_radial_excess_closing_speed_mps
                and abs(sample.angular_velocity) <= self.config.collision_max_angular_speed_radps
            ):
                collision = max(collision, self.config.collision_proximity_score)
            if (
                sample.nearest_lidar_distance <= self.config.collision_proximity_m
                and radial_closing_speed
                >= abs(sample.linear_velocity)
                + self.config.collision_radial_excess_closing_speed_mps
            ):
                collision = max(collision, self.config.collision_proximity_score)

        # A brief WAIT can make TTC and closing-speed estimates vanish before
        # the obstacle has actually cleared. Latch an actionable collision
        # warning for a bounded hold time and, after that, until the wider
        # collision sector reaches a distinct release distance.
        if collision >= self.config.collision_proximity_score:
            self._last_collision_risk_timestamp = sample.timestamp
        elif self._last_collision_risk_timestamp is not None:
            time_since_risk = sample.timestamp - self._last_collision_risk_timestamp
            if (
                time_since_risk <= self.config.collision_hold_s
                or collision_clearance < self.config.collision_release_distance_m
            ):
                collision = max(collision, self.config.collision_proximity_score)
            else:
                self._last_collision_risk_timestamp = None

        freeze_window = self._window(self.config.freeze_window_s)
        freeze = 0.0
        if self._covers(freeze_window, self.config.freeze_window_s) and not sample.goal_reached:
            displacement = path_displacement([item.position for item in freeze_window])
            motion_request_fraction = float(
                np.mean(
                    [
                        abs(item.base_linear_command) >= self.config.requested_motion_speed_mps
                        for item in freeze_window
                    ]
                )
            )
            requested_motion = (
                motion_request_fraction >= self.config.requested_motion_fraction
                or any(
                    item.planner_status in {PlannerStatus.NO_VALID_CONTROL, PlannerStatus.ABORTED}
                    for item in freeze_window
                )
            )
            if (
                sample.goal_distance > self.config.freeze_goal_distance_m
                and displacement < self.config.freeze_displacement_m
                and requested_motion
            ):
                freeze = 1.0

        oscillation_window = self._window(self.config.oscillation_window_s)
        oscillation = 0.0
        if self._covers(oscillation_window, self.config.oscillation_window_s):
            changes = angular_sign_changes(
                [item.angular_velocity for item in oscillation_window],
                self.config.angular_deadband_radps,
            )
            progress = goal_progress([item.goal_distance for item in oscillation_window])
            if (
                changes >= self.config.oscillation_sign_changes
                and progress < self.config.oscillation_progress_m
            ):
                oscillation = 1.0

        deadlock_window = self._window(self.config.deadlock_window_s)
        deadlock = 0.0
        if self._covers(deadlock_window, self.config.deadlock_window_s) and not sample.goal_reached:
            displacement = path_displacement([item.position for item in deadlock_window])
            progress = goal_progress([item.goal_distance for item in deadlock_window])
            mean_speed = float(np.mean([abs(item.linear_velocity) for item in deadlock_window]))
            nearby_blockage = (
                min(item.nearest_lidar_distance for item in deadlock_window)
                < self.config.deadlock_obstacle_distance_m
            )
            if (
                nearby_blockage
                and displacement < self.config.deadlock_displacement_m
                and progress < self.config.freeze_displacement_m
                and mean_speed < self.config.deadlock_speed_mps
            ):
                deadlock = 1.0

        return FailurePrediction(collision, freeze, oscillation, deadlock)
