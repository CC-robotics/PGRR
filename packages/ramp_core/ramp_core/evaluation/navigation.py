"""Pure navigation-status tracking used by ROS episode logging."""

from __future__ import annotations

from dataclasses import dataclass


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

        if any(status in {accepted, executing, canceling} for status in statuses):
            self.abort_since_s = None
            return False
        if aborted not in statuses:
            self.abort_since_s = None
            return False
        if self.abort_since_s is None or simulated_time_s < self.abort_since_s:
            self.abort_since_s = simulated_time_s
        return simulated_time_s - self.abort_since_s >= self.grace_s
