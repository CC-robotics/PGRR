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
class TemporalClosingSideConfig:
    """Validation-selected thresholds for observable crossing-flow evidence."""

    sector_min_degrees: float = 5.0
    sector_max_degrees: float = 60.0
    closing_delta_m: float = 0.20
    maximum_current_range_m: float = 4.0
    minimum_closing_beams: int = 5
    maximum_angular_speed_radps: float = 0.20

    def __post_init__(self) -> None:
        values = (
            self.sector_min_degrees,
            self.sector_max_degrees,
            self.closing_delta_m,
            self.maximum_current_range_m,
            self.maximum_angular_speed_radps,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("temporal closing-side thresholds must be finite")
        if not 0.0 <= self.sector_min_degrees < self.sector_max_degrees <= 90.0:
            raise ValueError("closing-side sector must satisfy 0 <= min < max <= 90 degrees")
        if self.closing_delta_m <= 0.0 or self.maximum_current_range_m <= 0.0:
            raise ValueError("closing delta and current-range limit must be positive")
        if isinstance(self.minimum_closing_beams, bool) or not isinstance(
            self.minimum_closing_beams, int
        ):
            raise ValueError("minimum closing beams must be an integer")
        if not 1 <= self.minimum_closing_beams <= 180:
            raise ValueError("minimum closing beams must lie in [1, 180]")
        if self.maximum_angular_speed_radps < 0.0:
            raise ValueError("maximum angular speed must be non-negative")


@dataclass(frozen=True, slots=True)
class TemporalClosingSideResult:
    """Mask intersection and evidence retained for online telemetry."""

    mask: npt.NDArray[np.bool_]
    right_closing_beams: int
    left_closing_beams: int
    right_occupied: bool
    left_occupied: bool
    rotation_gated: bool


@dataclass
class ObservableClosingSideLatch:
    """Retain reliable task-side flow evidence for one directional yield.

    A recovery BACKUP changes beam correspondence and can temporarily reduce
    the five-frame closing count even though the same flow still blocks the
    corridor. Reliable side observations therefore accumulate by union while
    the parent directional-yield latch is active. Rotation-gated observations
    neither add nor remove evidence. The parent latch's independently observed
    corridor-clear transition is the sole normal release condition.
    """

    right_occupied: bool = False
    left_occupied: bool = False

    @property
    def active(self) -> bool:
        return self.right_occupied or self.left_occupied

    def reset(self) -> None:
        self.right_occupied = False
        self.left_occupied = False

    def update(
        self,
        *,
        yield_active: bool,
        right_occupied: bool,
        left_occupied: bool,
        rotation_gated: bool,
    ) -> tuple[bool, bool]:
        """Update and return ``(right, left)`` retained occupancy flags."""

        if not yield_active:
            self.reset()
        elif not rotation_gated:
            self.right_occupied |= right_occupied
            self.left_occupied |= left_occupied
        return self.right_occupied, self.left_occupied


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


@dataclass(frozen=True, slots=True)
class BoundedSubgoalOption:
    """Bound learned temporary-goal execution before policy reconsideration.

    Nav2 goal submission and local replanning consume the initial settle
    interval.  A learned subgoal must then receive a separate execution
    interval before a successful planner result may complete the option.  A
    hard option limit prevents an active or failed planner result from holding
    recovery until the enclosing state-machine limit.

    ``legacy_action_interval_s`` preserves the former
    ``bc_action_interval_s`` override as an additional lower bound.  It can
    lengthen, but never shorten, the settle-plus-execution requirement.
    """

    settle_duration_s: float = 1.0
    minimum_execution_duration_s: float = 2.0
    maximum_duration_s: float = 6.0
    recovery_limit_s: float = 8.0
    legacy_action_interval_s: float = 0.5

    def __post_init__(self) -> None:
        values = (
            self.settle_duration_s,
            self.minimum_execution_duration_s,
            self.maximum_duration_s,
            self.recovery_limit_s,
            self.legacy_action_interval_s,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("bounded subgoal durations must be finite")
        if self.settle_duration_s < 0.0:
            raise ValueError("subgoal settle duration must be non-negative")
        if self.minimum_execution_duration_s <= 0.0:
            raise ValueError("subgoal execution duration must be positive")
        if self.legacy_action_interval_s < 0.0:
            raise ValueError("legacy BC action interval must be non-negative")
        if self.maximum_duration_s < self.earliest_completion_s:
            raise ValueError("maximum subgoal duration precedes earliest completion")
        if self.maximum_duration_s >= self.recovery_limit_s:
            raise ValueError("maximum subgoal duration must precede the recovery limit")

    @property
    def earliest_completion_s(self) -> float:
        """First instant at which planner success may complete the option."""

        return max(
            self.settle_duration_s + self.minimum_execution_duration_s,
            self.legacy_action_interval_s,
        )

    def is_complete(self, *, elapsed_s: float, planner_succeeded: bool) -> bool:
        """Return whether the subgoal may be reconsidered at this instant."""

        if not math.isfinite(elapsed_s) or elapsed_s < 0.0:
            raise ValueError("elapsed subgoal duration must be finite and non-negative")
        if elapsed_s < self.earliest_completion_s:
            return False
        return planner_succeeded or elapsed_s >= self.maximum_duration_s


@dataclass
class ObservableGoalProgressBudget:
    """Emit a reset pulse only after cumulative progress toward the task goal.

    Retreat never moves the reference backward, so returning to a previously
    reached point cannot repeatedly replenish a bounded recovery budget.
    """

    reset_progress_m: float = 0.25
    reference_distance_m: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.reset_progress_m) or self.reset_progress_m <= 0.0:
            raise ValueError("goal-progress reset distance must be finite and positive")
        if self.reference_distance_m is not None and (
            not math.isfinite(self.reference_distance_m) or self.reference_distance_m < 0.0
        ):
            raise ValueError("goal-progress reference must be finite and non-negative")

    @staticmethod
    def _validate_distance(distance_to_goal_m: float) -> None:
        if not math.isfinite(distance_to_goal_m) or distance_to_goal_m < 0.0:
            raise ValueError("distance to goal must be finite and non-negative")

    def progress_reached(self, distance_to_goal_m: float) -> bool:
        """Return a level signal without consuming unconfirmed progress."""

        self._validate_distance(distance_to_goal_m)
        if self.reference_distance_m is None:
            self.reference_distance_m = distance_to_goal_m
            return False
        return self.reference_distance_m - distance_to_goal_m >= self.reset_progress_m

    def acknowledge(self, distance_to_goal_m: float) -> None:
        """Consume progress only after NORMAL travel or a successful rejoin."""

        self._validate_distance(distance_to_goal_m)
        if self.reference_distance_m is not None and (
            self.reference_distance_m - distance_to_goal_m < self.reset_progress_m
        ):
            raise ValueError("cannot acknowledge less than the configured goal progress")
        self.reference_distance_m = distance_to_goal_m


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
class ObservableDirectionalYieldLatch:
    """Hold a social yield until the observable task-forward corridor clears.

    A momentary reduction in estimated TTC is not enough evidence that an
    approaching obstacle has passed.  The latch therefore starts from the
    deployable collision-risk estimate and releases only after a directional
    LiDAR sector exceeds ``release_clearance_m`` for consecutive observations.
    Missing scan coverage fails closed.  No pedestrian identity, trajectory,
    or simulator state is consumed.
    """

    trigger_threshold: float = 0.65
    release_clearance_m: float = 1.25
    release_frames: int = 3
    latched: bool = False
    clear_frames: int = 0
    last_observation_id: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.trigger_threshold) or not 0.0 <= self.trigger_threshold <= 1.0:
            raise ValueError("yield trigger threshold must lie in [0, 1]")
        if not math.isfinite(self.release_clearance_m) or self.release_clearance_m < 0.0:
            raise ValueError("yield release clearance must be finite and non-negative")
        if self.release_frames <= 0:
            raise ValueError("yield release frames must be positive")
        if self.clear_frames < 0:
            raise ValueError("yield clear-frame count must be non-negative")
        if not self.latched and self.clear_frames:
            raise ValueError("an inactive yield latch cannot retain clear frames")
        if self.last_observation_id is not None and self.last_observation_id < 0:
            raise ValueError("yield observation ID must be non-negative")

    def reset(self) -> None:
        """Clear all temporal state for a new navigation episode."""

        self.latched = False
        self.clear_frames = 0
        self.last_observation_id = None

    def update(
        self,
        *,
        collision_risk: float,
        forward_clearance_m: float | None,
        observation_id: int | None = None,
    ) -> bool:
        """Update the latch and return whether task-goal rejoin remains blocked."""

        if not math.isfinite(collision_risk) or not 0.0 <= collision_risk <= 1.0:
            raise ValueError("collision risk must lie in [0, 1]")
        if forward_clearance_m is not None and (
            not math.isfinite(forward_clearance_m) or forward_clearance_m < 0.0
        ):
            raise ValueError("forward clearance must be finite and non-negative when observed")
        if observation_id is not None and observation_id < 0:
            raise ValueError("yield observation ID must be non-negative")
        if collision_risk >= self.trigger_threshold:
            self.latched = True
            self.clear_frames = 0
            self.last_observation_id = observation_id
            return True
        if not self.latched:
            return False
        if observation_id is not None and observation_id == self.last_observation_id:
            return True
        self.last_observation_id = observation_id
        if forward_clearance_m is None or forward_clearance_m < self.release_clearance_m:
            self.clear_frames = 0
            return True
        self.clear_frames += 1
        if self.clear_frames >= self.release_frames:
            self.reset()
        return self.latched


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
    escape_reason: str | None = None
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

    def reset(self) -> None:
        """Clear all episode-local threat, retreat, and recurrence state."""

        self.threat_indices = ()
        self.activation_coordinate_m = None
        self.previous_activation_coordinate_m = None
        self.recurrence_count = 0
        self.escape_required = False
        self.escape_reason = None
        self.backup_required = False

    def require_escape_if_retreat_unavailable(self, *, retreat_is_safe: bool) -> bool:
        """Escalate an unresolved yield after its safe retreat is exhausted.

        ``backup_required`` captures the longitudinal distance budget, while
        ``retreat_is_safe`` is supplied by the authoritative planning mask.
        This method never makes an action legal; it only selects the existing
        planning-constrained escape branch.
        """

        if not self.active or self.escape_required:
            return self.escape_required
        if self.backup_required and retreat_is_safe:
            return False
        self.escape_required = True
        self.escape_reason = (
            "retreat_distance_exhausted" if not self.backup_required else "retreat_planning_masked"
        )
        return True

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
            self.escape_reason = None

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
                self.escape_required = False
                self.escape_reason = None
                self.backup_required = False
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
                    if self.escape_required:
                        self.escape_reason = "recurrent_flow_without_progress"
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


def constrain_directional_yield_motion(
    mask: npt.NDArray[np.bool_],
    *,
    pose: Pose2D,
    path_heading_rad: float,
    backup_distance_m: float,
    maximum_forward_progress_m: float = 0.05,
) -> npt.NDArray[np.bool_]:
    """During an active yield, retain only non-forward legal translations.

    The function only intersects an existing planning mask.  Endpoints are
    projected onto the observable local path tangent; a learned subgoal or
    BACKUP cannot advance toward the blocked corridor until the independent
    directional-clearance latch releases. WAIT remains untouched, while task
    rejoin actions are disabled explicitly.
    """

    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    values = (path_heading_rad, backup_distance_m, maximum_forward_progress_m)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("directional-yield geometry must be finite")
    if backup_distance_m < 0.0 or maximum_forward_progress_m < 0.0:
        raise ValueError("directional-yield distances must be non-negative")
    tangent = math.cos(path_heading_rad), math.sin(path_heading_rad)

    def advances_path(endpoint: Pose2D) -> bool:
        progress = (endpoint.x - pose.x) * tangent[0] + (endpoint.y - pose.y) * tangent[1]
        return progress > maximum_forward_progress_m + 1.0e-9

    for action in ACTIONS[:WAIT_ACTION_ID]:
        endpoint = action.target_pose(pose)
        assert endpoint is not None
        if advances_path(endpoint):
            constrained[action.action_id] = False
    backup_endpoint = Pose2D(
        pose.x - backup_distance_m * math.cos(pose.yaw),
        pose.y - backup_distance_m * math.sin(pose.yaw),
        pose.yaw,
    )
    if advances_path(backup_endpoint):
        constrained[BACKUP_ACTION_ID] = False
    constrained[REPLAN_ACTION_ID] = False
    constrained[CONTINUE_ACTION_ID] = False
    return constrained


def constrain_temporal_closing_side(
    mask: npt.NDArray[np.bool_],
    lidar_stack: npt.ArrayLike,
    *,
    angle_min_rad: float,
    angle_max_rad: float,
    pose: Pose2D,
    path_heading_rad: float,
    angular_speed_radps: float,
    minimum_lateral_displacement_m: float,
    config: TemporalClosingSideConfig | None = None,
) -> TemporalClosingSideResult:
    """Mask task-lateral subgoals toward an observably closing side flow.

    The oldest and newest samples of the fixed five-frame, 180-beam policy
    input are compared beam-wise. Beam bearings and action endpoints are both
    expressed in the local task-path frame, so turning the robot does not swap
    the physical yield sides. The helper only intersects ``mask``: it never
    enables an action, and WAIT/BACKUP/REPLAN remain exactly as supplied.

    Beam correspondence is not reliable while the robot is rotating. Above
    the configured angular-speed gate, valid inputs therefore return an
    unchanged defensive copy and explicit telemetry evidence.
    """

    if config is None:
        config = TemporalClosingSideConfig()
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    lidar = np.asarray(lidar_stack, dtype=np.float64)
    if lidar.shape != (5, 180):
        raise ValueError("lidar stack must have shape (5, 180)")
    geometry = (
        angle_min_rad,
        angle_max_rad,
        pose.x,
        pose.y,
        pose.yaw,
        path_heading_rad,
        angular_speed_radps,
    )
    if not all(math.isfinite(value) for value in geometry):
        raise ValueError("closing-side scan geometry and motion must be finite")
    if angle_max_rad <= angle_min_rad:
        raise ValueError("scan angle_max must be greater than angle_min")
    if not math.isfinite(minimum_lateral_displacement_m) or minimum_lateral_displacement_m <= 0.0:
        raise ValueError("minimum lateral displacement must be finite and positive")

    if abs(angular_speed_radps) > config.maximum_angular_speed_radps + 1.0e-12:
        return TemporalClosingSideResult(constrained, 0, 0, False, False, True)

    beam_angles = np.linspace(angle_min_rad, angle_max_rad, 180, dtype=np.float64)
    task_relative_angles = np.arctan2(
        np.sin(pose.yaw + beam_angles - path_heading_rad),
        np.cos(pose.yaw + beam_angles - path_heading_rad),
    )
    minimum_sector_rad = math.radians(config.sector_min_degrees)
    maximum_sector_rad = math.radians(config.sector_max_degrees)
    oldest = lidar[0]
    newest = lidar[-1]
    valid = (
        np.isfinite(oldest)
        & np.isfinite(newest)
        & (oldest > 0.0)
        & (newest > 0.0)
        & (newest <= config.maximum_current_range_m)
    )
    closing = valid & (oldest - newest >= config.closing_delta_m - 1.0e-12)
    right_sector = (task_relative_angles >= -maximum_sector_rad) & (
        task_relative_angles <= -minimum_sector_rad
    )
    left_sector = (task_relative_angles >= minimum_sector_rad) & (
        task_relative_angles <= maximum_sector_rad
    )
    right_closing_beams = int(np.count_nonzero(closing & right_sector))
    left_closing_beams = int(np.count_nonzero(closing & left_sector))
    right_occupied = right_closing_beams >= config.minimum_closing_beams
    left_occupied = left_closing_beams >= config.minimum_closing_beams

    constrained = constrain_task_lateral_sides(
        constrained,
        pose=pose,
        path_heading_rad=path_heading_rad,
        minimum_lateral_displacement_m=minimum_lateral_displacement_m,
        right_occupied=right_occupied,
        left_occupied=left_occupied,
    )

    return TemporalClosingSideResult(
        constrained,
        right_closing_beams,
        left_closing_beams,
        right_occupied,
        left_occupied,
        False,
    )


def constrain_task_lateral_sides(
    mask: npt.NDArray[np.bool_],
    *,
    pose: Pose2D,
    path_heading_rad: float,
    minimum_lateral_displacement_m: float,
    right_occupied: bool,
    left_occupied: bool,
) -> npt.NDArray[np.bool_]:
    """Intersect subgoals with retained occupancy in the task-path frame.

    Special actions are copied unchanged. In particular, this pure helper
    cannot remove or introduce WAIT/BACKUP/REPLAN semantics, and it can never
    re-authorize an action rejected by an earlier planning or LiDAR mask.
    """

    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    geometry = (pose.x, pose.y, pose.yaw, path_heading_rad, minimum_lateral_displacement_m)
    if not all(math.isfinite(value) for value in geometry):
        raise ValueError("task-lateral side geometry must be finite")
    if minimum_lateral_displacement_m <= 0.0:
        raise ValueError("minimum lateral displacement must be positive")
    if not right_occupied and not left_occupied:
        return constrained

    normal = -math.sin(path_heading_rad), math.cos(path_heading_rad)
    for action in ACTIONS[:WAIT_ACTION_ID]:
        endpoint = action.target_pose(pose)
        assert endpoint is not None
        lateral_displacement = (endpoint.x - pose.x) * normal[0] + (endpoint.y - pose.y) * normal[1]
        toward_right = lateral_displacement <= -minimum_lateral_displacement_m + 1.0e-9
        toward_left = lateral_displacement >= minimum_lateral_displacement_m - 1.0e-9
        if (right_occupied and toward_right) or (left_occupied and toward_left):
            constrained[action.action_id] = False
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


def effective_recovery_path_deviation(
    *,
    policy_type: str,
    directional_yield_latched: bool,
    consecutive_recoveries: int,
    recurrent_escape_after_recoveries: int,
    normal_maximum_deviation_m: float,
    recurrent_maximum_deviation_m: float,
) -> float:
    """Select the wider path envelope only for recurrent learned yielding.

    The returned value controls only the path-corridor regularizer. Static-map
    occupancy, observable LiDAR clearance, directional no-forward motion, and
    net-retreat constraints remain independent intersections of the action
    mask and therefore cannot be relaxed by this helper.
    """

    if policy_type not in {"heuristic", "expert", "bc"}:
        raise ValueError("policy_type must be heuristic, expert, or bc")
    if consecutive_recoveries < 0:
        raise ValueError("consecutive recoveries must be non-negative")
    if recurrent_escape_after_recoveries <= 0:
        raise ValueError("recurrent escape threshold must be positive")
    deviations = (normal_maximum_deviation_m, recurrent_maximum_deviation_m)
    if not all(math.isfinite(value) and value > 0.0 for value in deviations):
        raise ValueError("recovery path deviations must be finite and positive")
    if recurrent_maximum_deviation_m < normal_maximum_deviation_m:
        raise ValueError("recurrent recovery path deviation must not be smaller than normal")
    recurrent_learned_yield = (
        policy_type == "bc"
        and directional_yield_latched
        and consecutive_recoveries >= recurrent_escape_after_recoveries
    )
    return recurrent_maximum_deviation_m if recurrent_learned_yield else normal_maximum_deviation_m


def recurrent_yield_lateral_action_ids(
    *,
    pose: Pose2D,
    path_heading_rad: float,
    minimum_lateral_displacement_m: float,
) -> tuple[int, ...]:
    """Return subgoals with sufficient displacement normal to the task path.

    Recovery actions are expressed in the robot frame, so a non-zero action
    angle is not necessarily lateral to the navigation path once the robot has
    turned during an earlier recovery.  Classifying the endpoint in the local
    path frame keeps recurrent-yield escalation tied to observable geometry.
    """

    if not math.isfinite(path_heading_rad):
        raise ValueError("path heading must be finite")
    if not math.isfinite(minimum_lateral_displacement_m) or minimum_lateral_displacement_m <= 0.0:
        raise ValueError("minimum lateral displacement must be finite and positive")
    normal = -math.sin(path_heading_rad), math.cos(path_heading_rad)
    lateral_ids: list[int] = []
    for action in ACTIONS[:WAIT_ACTION_ID]:
        endpoint = action.target_pose(pose)
        assert endpoint is not None
        lateral_displacement = abs(
            (endpoint.x - pose.x) * normal[0] + (endpoint.y - pose.y) * normal[1]
        )
        if lateral_displacement + 1.0e-9 >= minimum_lateral_displacement_m:
            lateral_ids.append(action.action_id)
    return tuple(lateral_ids)


def constrain_recurrent_yield_escape(
    mask: npt.NDArray[np.bool_],
    *,
    escape_required: bool,
    pose: Pose2D,
    path_heading_rad: float,
    minimum_lateral_displacement_m: float,
) -> npt.NDArray[np.bool_]:
    """Escalate a recurrent yield loop to a masked lateral escape or REPLAN.

    Lateral subgoals are classified by endpoint displacement normal to the
    observable local path tangent, not by their robot-frame action angle.  The
    restriction is applied only when at least one such already-valid subgoal
    or REPLAN exists. Otherwise the original mask is returned so the caller
    retains a safe WAIT/BACKUP fallback.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not escape_required:
        return constrained
    escape_ids = (
        *recurrent_yield_lateral_action_ids(
            pose=pose,
            path_heading_rad=path_heading_rad,
            minimum_lateral_displacement_m=minimum_lateral_displacement_m,
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
