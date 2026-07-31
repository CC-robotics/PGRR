"""Temporal composition rules for bounded recovery options."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
)
from ramp_core.observations import HumanState
from ramp_core.types import Pose2D


@dataclass
class PrivilegedYieldOption:
    """Commit to longitudinal yielding until approaching humans have passed."""

    task_heading_rad: float
    passed_margin_m: float = 0.5
    minimum_closing_speed_mps: float = 0.05
    maximum_retreat_m: float = 1.4
    recurrence_progress_m: float = 0.75
    maximum_recurrences_without_progress: int = 1
    threat_indices: tuple[int, ...] = ()
    activation_coordinate_m: float | None = None
    previous_activation_coordinate_m: float | None = None
    recurrence_count: int = 0
    escape_required: bool = False
    backup_required: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.task_heading_rad):
            raise ValueError("task heading must be finite")
        if (
            self.passed_margin_m < 0.0
            or self.minimum_closing_speed_mps < 0.0
            or self.maximum_retreat_m <= 0.0
            or self.recurrence_progress_m <= 0.0
        ):
            raise ValueError("yield margins and speeds must be non-negative")
        if self.maximum_recurrences_without_progress <= 0:
            raise ValueError("maximum recurrences without progress must be positive")

    @property
    def active(self) -> bool:
        return bool(self.threat_indices)

    def update(
        self,
        robot: Pose2D,
        humans: tuple[HumanState, ...],
        *,
        collision_risk: bool,
    ) -> bool:
        """Update the option and return whether longitudinal yielding is active."""
        tangent = math.cos(self.task_heading_rad), math.sin(self.task_heading_rad)
        robot_coordinate = robot.x * tangent[0] + robot.y * tangent[1]
        if (
            self.previous_activation_coordinate_m is not None
            and robot_coordinate - self.previous_activation_coordinate_m
            >= self.recurrence_progress_m
        ):
            self.recurrence_count = 0
            self.escape_required = False

        def longitudinal(position: tuple[float, float]) -> float:
            return (position[0] - robot.x) * tangent[0] + (position[1] - robot.y) * tangent[1]

        if self.threat_indices:
            valid = tuple(index for index in self.threat_indices if index < len(humans))
            passed = valid and all(
                longitudinal(humans[index].position) <= -self.passed_margin_m for index in valid
            )
            receding = (
                valid
                and not collision_risk
                and all(
                    humans[index].velocity[0] * tangent[0] + humans[index].velocity[1] * tangent[1]
                    >= self.minimum_closing_speed_mps
                    for index in valid
                )
            )
            if passed or receding or not valid:
                self.threat_indices = ()
                self.activation_coordinate_m = None
            else:
                self.threat_indices = valid
        if not self.threat_indices and collision_risk:
            new_threats = tuple(
                index
                for index, human in enumerate(humans)
                if longitudinal(human.position) > 0.0
                and human.velocity[0] * tangent[0] + human.velocity[1] * tangent[1]
                <= -self.minimum_closing_speed_mps
            )
            if new_threats:
                if (
                    self.previous_activation_coordinate_m is not None
                    and robot_coordinate - self.previous_activation_coordinate_m
                    < self.recurrence_progress_m
                ):
                    self.recurrence_count += 1
                    self.escape_required = (
                        self.recurrence_count >= self.maximum_recurrences_without_progress
                    )
                self.threat_indices = new_threats
                self.activation_coordinate_m = robot_coordinate
                self.previous_activation_coordinate_m = robot_coordinate
        self.backup_required = bool(
            self.threat_indices
            and self.activation_coordinate_m is not None
            and self.activation_coordinate_m - robot_coordinate < self.maximum_retreat_m
        )
        return self.active


def should_continue_recovery_option(
    *,
    policy_type: str,
    action_id: int,
    action_complete: bool,
    failure_score: float,
    tau_off: float,
    option_elapsed_s: float,
    maximum_option_duration_s: float,
) -> bool:
    """Keep replanning within RECOVERY until an expert explicitly rejoins."""
    if not 0.0 <= failure_score <= 1.0 or not 0.0 <= tau_off <= 1.0:
        raise ValueError("failure score and tau_off must lie in [0, 1]")
    if option_elapsed_s < 0.0 or maximum_option_duration_s < 0.0:
        raise ValueError("option durations must be non-negative")
    if not action_complete or option_elapsed_s >= maximum_option_duration_s:
        return False
    if failure_score >= tau_off:
        return True
    return policy_type == "expert" and action_id not in {
        CONTINUE_ACTION_ID,
        REPLAN_ACTION_ID,
    }


def constrain_rejoin_actions(
    mask: npt.NDArray[np.bool_],
    *,
    collision_risk: float,
    release_threshold: float,
) -> npt.NDArray[np.bool_]:
    """Disable task-goal rejoin actions while collision risk remains latched."""
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not 0.0 <= collision_risk <= 1.0 or not 0.0 <= release_threshold <= 1.0:
        raise ValueError("collision risk and release threshold must lie in [0, 1]")
    if collision_risk >= release_threshold:
        constrained[CONTINUE_ACTION_ID] = False
        constrained[REPLAN_ACTION_ID] = False
    return constrained


def constrain_recurrent_yield_escape(
    mask: npt.NDArray[np.bool_],
    *,
    escape_required: bool,
) -> npt.NDArray[np.bool_]:
    """Escalate a recurrent yield loop to a masked lateral escape or REPLAN.

    The restriction is applied only when at least one already-valid lateral
    subgoal or REPLAN exists. Otherwise the original mask is returned so the
    caller retains a safe WAIT/BACKUP fallback.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not escape_required:
        return constrained
    escape_ids = (
        *(
            action.action_id
            for action in ACTIONS[:WAIT_ACTION_ID]
            if action.angle_degrees is not None and action.angle_degrees != 0
        ),
        REPLAN_ACTION_ID,
    )
    if not any(bool(constrained[action_id]) for action_id in escape_ids):
        return constrained
    permitted = np.zeros(ACTION_COUNT, dtype=np.bool_)
    permitted[list(escape_ids)] = True
    return constrained & permitted


def constrain_stalled_wait(
    mask: npt.NDArray[np.bool_],
    *,
    consecutive_waits: int,
    wait_budget: int,
) -> npt.NDArray[np.bool_]:
    """Force a safe escape action after a bounded number of no-progress waits.

    WAIT remains available when it is the only safe choice. Once its budget is
    exhausted, it is disabled only if at least one subgoal or BACKUP action is
    valid. This turns repeated yielding into a bounded recovery option without
    weakening the planning mask.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if consecutive_waits < 0 or wait_budget <= 0:
        raise ValueError("wait counters must be non-negative and budget positive")
    escape_available = bool(
        constrained[:WAIT_ACTION_ID].any()
        or constrained[BACKUP_ACTION_ID]
        or constrained[REPLAN_ACTION_ID]
    )
    if consecutive_waits >= wait_budget and escape_available:
        constrained[WAIT_ACTION_ID] = False
    return constrained


def constrain_repeated_replan(
    mask: npt.NDArray[np.bool_],
    *,
    replan_count: int,
    replan_budget: int,
) -> npt.NDArray[np.bool_]:
    """Prevent repeated REPLAN requests from starving executable options."""
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if replan_count < 0 or replan_budget <= 0:
        raise ValueError("replan count must be non-negative and budget positive")
    alternatives = constrained.copy()
    alternatives[REPLAN_ACTION_ID] = False
    if replan_count >= replan_budget and bool(alternatives.any()):
        constrained[REPLAN_ACTION_ID] = False
    return constrained
