"""Pure navigation-status tracking used by ROS episode logging."""

from __future__ import annotations

from dataclasses import dataclass


def navigation_status_is_active(
    statuses: tuple[int, ...],
    *,
    accepted: int = 1,
    executing: int = 2,
    canceling: int = 3,
) -> bool:
    """Return whether a status array contains a live navigation goal."""
    return any(status in {accepted, executing, canceling} for status in statuses)


def timeout_is_invalid_reset(
    *,
    planner_ever_active: bool,
    maximum_start_displacement_m: float,
    movement_threshold_m: float = 0.05,
) -> bool:
    """Identify episodes whose navigation goal never became executable."""
    if maximum_start_displacement_m < 0.0 or movement_threshold_m < 0.0:
        raise ValueError("displacements must be non-negative")
    return not planner_ever_active and maximum_start_displacement_m < movement_threshold_m


@dataclass
class PlannerAbortTracker:
    """Detect a terminal Nav2 abort after a simulated-time grace interval.

    GoalStatusArray retains old terminal goals while a replacement goal is
    active. An abort is terminal only when no accepted, executing, or
    canceling goal is present for the full grace interval.
    """

    grace_s: float
    abort_since_s: float | None = None

    def __post_init__(self) -> None:
        if self.grace_s < 0.0:
            raise ValueError("grace_s must be non-negative")

    def update(
        self,
        *,
        statuses: tuple[int, ...],
        simulated_time_s: float,
        accepted: int = 1,
        executing: int = 2,
        canceling: int = 3,
        aborted: int = 6,
    ) -> bool:
        """Return true when an unopposed abort has exceeded ``grace_s``."""

        if navigation_status_is_active(
            statuses,
            accepted=accepted,
            executing=executing,
            canceling=canceling,
        ):
            self.abort_since_s = None
            return False
        if aborted not in statuses:
            self.abort_since_s = None
            return False
        if self.abort_since_s is None or simulated_time_s < self.abort_since_s:
            self.abort_since_s = simulated_time_s
        return simulated_time_s - self.abort_since_s >= self.grace_s
