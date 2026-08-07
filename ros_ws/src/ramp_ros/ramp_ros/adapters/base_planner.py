"""Planner adapter interface used by recovery business logic."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ramp_core.types import PlannerStatus, Pose2D, Velocity2D


class PlannerAdapter(ABC):
    @abstractmethod
    def set_navigation_goal(self, goal: Pose2D) -> None:
        """Submit and retain an original navigation goal."""

    @abstractmethod
    def set_recovery_goal(self, goal: Pose2D) -> None:
        """Preempt navigation with a temporary recovery goal."""

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current goal."""

    @abstractmethod
    def get_status(self) -> PlannerStatus:
        """Return a backend-neutral status."""

    @abstractmethod
    def get_last_command(self) -> Velocity2D:
        """Return the most recent planner command."""
