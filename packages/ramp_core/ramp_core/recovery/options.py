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


@dataclass(frozen=True, slots=True)
class BoundedBackupOption:
    """Closed-loop completion rule for one planning-validated retreat.

    The planning mask validates a fixed rear segment before BACKUP is chosen.
    This option keeps the command active for at least ``minimum_duration_s``,
    releases it once observable clearance has improved enough, and imposes a
    hard time bound.  Construction fails when the largest commanded retreat
    could be longer than the segment validated by the action mask.
    """

    minimum_duration_s: float = 0.8
    maximum_duration_s: float = 3.0
    speed_mps: float = 0.15
    clearance_improvement_m: float = 0.25
    mask_validated_distance_m: float = 0.45

    def __post_init__(self) -> None:
        values = (
            self.minimum_duration_s,
            self.maximum_duration_s,
            self.speed_mps,
            self.clearance_improvement_m,
            self.mask_validated_distance_m,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("bounded BACKUP parameters must be finite")
        if self.minimum_duration_s < 0.0:
            raise ValueError("minimum BACKUP duration must be non-negative")
        if self.maximum_duration_s < self.minimum_duration_s:
            raise ValueError("maximum BACKUP duration must not precede its minimum")
        if self.speed_mps <= 0.0 or self.mask_validated_distance_m <= 0.0:
            raise ValueError("BACKUP speed and validated distance must be positive")
        if self.clearance_improvement_m < 0.0:
            raise ValueError("BACKUP clearance improvement must be non-negative")
        if self.maximum_command_distance_m > self.mask_validated_distance_m + 1.0e-9:
            raise ValueError(
                "maximum BACKUP command distance exceeds the action-mask validated segment"
            )

    @property
    def maximum_command_distance_m(self) -> float:
        """Largest ideal-kinematic retreat commanded by this option."""
        return self.speed_mps * self.maximum_duration_s

    def is_complete(
        self,
        *,
        elapsed_s: float,
        start_clearance_m: float | None,
        current_clearance_m: float | None,
    ) -> bool:
        """Return whether BACKUP should release at the current observation.

        Missing clearance observations cannot trigger an early release; the
        hard maximum duration still terminates the option.  This helper does
        not authorize motion, so the online safety stop remains authoritative.
        """
        if not math.isfinite(elapsed_s) or elapsed_s < 0.0:
            raise ValueError("elapsed BACKUP duration must be finite and non-negative")
        for name, clearance in (
            ("start", start_clearance_m),
            ("current", current_clearance_m),
        ):
            if clearance is not None and (not math.isfinite(clearance) or clearance < 0.0):
                raise ValueError(f"{name} BACKUP clearance must be finite and non-negative")
        if elapsed_s >= self.maximum_duration_s:
            return True
        if elapsed_s < self.minimum_duration_s:
            return False
        if start_clearance_m is None or current_clearance_m is None:
            return False
        return current_clearance_m - start_clearance_m >= self.clearance_improvement_m


@dataclass
class ObservableNetRetreatGuard:
    """Bound policy-directed retreat relative to achieved task progress.

    The guard projects the robot pose onto the fixed start-to-goal task axis
    and remembers the furthest coordinate reached.  A policy option is legal
    only when its endpoint would remain inside the configured net-retreat
    budget.  This uses robot odometry and the task goal only; it neither
    consumes privileged actor state nor relaxes a planning or LiDAR constraint.
    The emergency controller may also consult the guard for its optional
    BACKUP escape; STOP remains available unconditionally.
    """

    task_heading_rad: float
    maximum_net_retreat_m: float = 1.4
    best_task_coordinate_m: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.task_heading_rad):
            raise ValueError("task heading must be finite")
        if not math.isfinite(self.maximum_net_retreat_m) or self.maximum_net_retreat_m <= 0.0:
            raise ValueError("maximum net retreat must be finite and positive")
        if self.best_task_coordinate_m is not None and not math.isfinite(
            self.best_task_coordinate_m
        ):
            raise ValueError("best task coordinate must be finite")

    def task_coordinate(self, pose: Pose2D) -> float:
        """Return the observable longitudinal task coordinate of ``pose``."""

        return pose.x * math.cos(self.task_heading_rad) + pose.y * math.sin(self.task_heading_rad)

    def observe(self, pose: Pose2D) -> float:
        """Update the progress high-water mark and return current net retreat."""

        coordinate = self.task_coordinate(pose)
        if self.best_task_coordinate_m is None:
            self.best_task_coordinate_m = coordinate
        else:
            self.best_task_coordinate_m = max(self.best_task_coordinate_m, coordinate)
        return self.best_task_coordinate_m - coordinate

    def backup_permitted(self, pose: Pose2D, *, backup_distance_m: float) -> bool:
        """Return whether a full reverse segment stays within the retreat cap."""

        if not math.isfinite(backup_distance_m) or backup_distance_m < 0.0:
            raise ValueError("backup distance must be finite and non-negative")
        endpoint = Pose2D(
            pose.x - backup_distance_m * math.cos(pose.yaw),
            pose.y - backup_distance_m * math.sin(pose.yaw),
            pose.yaw,
        )
        return self.endpoint_permitted(pose, endpoint)

    def endpoint_permitted(self, pose: Pose2D, endpoint: Pose2D) -> bool:
        """Return whether an option endpoint respects achieved task progress."""

        self.observe(pose)
        assert self.best_task_coordinate_m is not None
        endpoint_retreat = self.best_task_coordinate_m - self.task_coordinate(endpoint)
        return endpoint_retreat <= self.maximum_net_retreat_m + 1.0e-9


@dataclass
class ObservableSubgoalStallGuard:
    """Escalate a repeatedly stationary learned subgoal to a non-subgoal option."""

    retry_budget: int = 4
    minimum_displacement_m: float = 0.08
    action_id: int | None = None
    reference_position: tuple[float, float] | None = None
    repeated_decisions: int = 0
    escape_required: bool = False

    def __post_init__(self) -> None:
        if self.retry_budget <= 0:
            raise ValueError("subgoal retry budget must be positive")
        if not math.isfinite(self.minimum_displacement_m) or self.minimum_displacement_m < 0.0:
            raise ValueError("subgoal displacement threshold must be finite and non-negative")

    def reset(self) -> None:
        self.action_id = None
        self.reference_position = None
        self.repeated_decisions = 0
        self.escape_required = False

    def observe_decision(self, action_id: int, pose: Pose2D) -> None:
        """Update the guard after selecting an action from deployable observations."""

        if not 0 <= action_id < ACTION_COUNT:
            raise ValueError(f"action_id must be in [0, {ACTION_COUNT - 1}]")
        if action_id >= WAIT_ACTION_ID:
            if action_id in {BACKUP_ACTION_ID, REPLAN_ACTION_ID}:
                self.reset()
            return
        position = (pose.x, pose.y)
        moved = (
            self.reference_position is None
            or math.dist(position, self.reference_position) >= self.minimum_displacement_m
        )
        if action_id != self.action_id or moved:
            self.action_id = action_id
            self.reference_position = position
            self.repeated_decisions = 1
        else:
            self.repeated_decisions += 1
        if self.repeated_decisions >= self.retry_budget:
            self.escape_required = True


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


def constrain_stalled_rejoin(
    mask: npt.NDArray[np.bool_],
    *,
    escape_required: bool,
) -> npt.NDArray[np.bool_]:
    """Prevent a no-progress rejoin retry from selecting CONTINUE again.

    The state machine requests a recovery retry only after the restored task
    goal failed to produce progress for its full rejoin window.  Re-submitting
    the same CONTINUE action is therefore a no-op loop.  Disable it only when
    a planning-valid subgoal, BACKUP, or REPLAN alternative exists; WAIT stays
    available as the safety fallback but does not by itself justify masking.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not escape_required:
        return constrained
    escape_available = bool(
        constrained[:WAIT_ACTION_ID].any()
        or constrained[BACKUP_ACTION_ID]
        or constrained[REPLAN_ACTION_ID]
    )
    if escape_available:
        constrained[CONTINUE_ACTION_ID] = False
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


def ensure_safe_wait_fallback(
    mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.bool_]:
    """Make an action mask non-empty without authorizing any motion.

    This fail-closed invariant is applied after every optional recovery
    constraint.  If independently valid restrictions eliminate all actions,
    only WAIT is restored; subgoals, BACKUP, REPLAN, and CONTINUE remain
    masked.  A non-empty mask is returned unchanged (apart from a defensive
    copy), so this helper never weakens a planning or safety decision.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not bool(constrained.any()):
        constrained[WAIT_ACTION_ID] = True
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


def constrain_repeated_backup(
    mask: npt.NDArray[np.bool_],
    *,
    backup_count: int,
    backup_budget: int,
) -> npt.NDArray[np.bool_]:
    """Bound no-progress retreats when a planning-valid escape exists.

    BACKUP remains available when it is the only safe translational option.
    Once the budget is exhausted, it is disabled only when the existing
    planning mask contains a subgoal or REPLAN.  The helper therefore cannot
    manufacture an unsafe action or weaken any collision clearance.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if backup_count < 0 or backup_budget <= 0:
        raise ValueError("backup count must be non-negative and budget positive")
    planned_escape_available = bool(
        constrained[:WAIT_ACTION_ID].any() or constrained[REPLAN_ACTION_ID]
    )
    if backup_count >= backup_budget and planned_escape_available:
        constrained[BACKUP_ACTION_ID] = False
    return constrained


def constrain_net_retreat(
    mask: npt.NDArray[np.bool_],
    *,
    guard: ObservableNetRetreatGuard,
    pose: Pose2D,
    backup_distance_m: float,
) -> npt.NDArray[np.bool_]:
    """Remove policy actions whose endpoints exceed the net-retreat cap."""

    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    for action in ACTIONS[:WAIT_ACTION_ID]:
        target = action.target_pose(pose)
        assert target is not None
        if not guard.endpoint_permitted(pose, target):
            constrained[action.action_id] = False
    if not guard.backup_permitted(pose, backup_distance_m=backup_distance_m):
        constrained[BACKUP_ACTION_ID] = False
    return constrained


def constrain_stalled_subgoals(
    mask: npt.NDArray[np.bool_],
    *,
    escape_required: bool,
) -> npt.NDArray[np.bool_]:
    """Temporarily remove subgoals after repeated stationary replanning."""

    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if escape_required:
        constrained[:WAIT_ACTION_ID] = False
    return constrained
