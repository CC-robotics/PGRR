"""Deterministic failure-specific heuristic over the fixed, masked action space."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.action_mask import validate_selected_action
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
    RecoveryActionKind,
)
from ramp_core.failure.labels import FailureType
from ramp_core.observations import RecoveryObservation
from ramp_core.types import PlannerStatus, RecoveryDecision


@dataclass(frozen=True, slots=True)
class HeuristicRecoveryConfig:
    side_clearance_ratio: float = 1.25
    collision_wait_clearance_m: float = 1.3
    collision_close_clearance_m: float = 0.60
    collision_emergency_wait_clearance_m: float = 0.5
    preferred_subgoal_radius_m: float = 1.0
    minimum_subgoal_progress_m: float = 0.15
    path_alignment_weight: float = 1.0
    goal_alignment_weight: float = 0.5
    progress_reward_weight: float = 0.4
    clearance_reward_weight: float = 0.2
    radius_preference_weight: float = 0.35
    side_cooldown_decisions: int = 4
    freeze_subgoal_after_decisions: int = 2
    freeze_max_backup_decisions: int = 6
    deadlock_backup_after_decisions: int = 2
    deadlock_replan_after_decisions: int = 4

    def __post_init__(self) -> None:
        if self.side_clearance_ratio <= 1.0:
            raise ValueError("side_clearance_ratio must be greater than one")
        if self.preferred_subgoal_radius_m <= 0.0:
            raise ValueError("preferred_subgoal_radius_m must be positive")
        weights = (
            self.minimum_subgoal_progress_m,
            self.path_alignment_weight,
            self.goal_alignment_weight,
            self.progress_reward_weight,
            self.clearance_reward_weight,
            self.radius_preference_weight,
        )
        if any(value < 0.0 for value in weights):
            raise ValueError("subgoal scoring parameters must be non-negative")
        if self.collision_wait_clearance_m <= 0.0:
            raise ValueError("collision_wait_clearance_m must be positive")
        if not 0.0 < self.collision_close_clearance_m <= self.collision_wait_clearance_m:
            raise ValueError(
                "collision_close_clearance_m must be positive and no greater than "
                "collision_wait_clearance_m"
            )
        if not 0.0 < self.collision_emergency_wait_clearance_m <= self.collision_wait_clearance_m:
            raise ValueError(
                "collision_emergency_wait_clearance_m must be positive and no greater "
                "than collision_wait_clearance_m"
            )
        counts = (
            self.side_cooldown_decisions,
            self.freeze_subgoal_after_decisions,
            self.freeze_max_backup_decisions,
            self.deadlock_backup_after_decisions,
            self.deadlock_replan_after_decisions,
        )
        if any(value < 0 for value in counts):
            raise ValueError("heuristic decision counts must be non-negative")
        if self.deadlock_replan_after_decisions < self.deadlock_backup_after_decisions:
            raise ValueError("deadlock replan threshold must not precede backup threshold")
        if self.freeze_max_backup_decisions < self.freeze_subgoal_after_decisions:
            raise ValueError("freeze backup limit must not precede its subgoal threshold")


class HeuristicRecoveryPolicy:
    def __init__(self, config: HeuristicRecoveryConfig | None = None) -> None:
        self.config = config if config is not None else HeuristicRecoveryConfig()
        self._decision_index = 0
        self._last_side = 0
        self._last_side_decision = -(10**9)
        self._deadlock_decisions = 0
        self._collision_decisions = 0
        self._freeze_decisions = 0

    def reset(self) -> None:
        self._decision_index = 0
        self._last_side = 0
        self._last_side_decision = -(10**9)
        self._deadlock_decisions = 0
        self._collision_decisions = 0
        self._freeze_decisions = 0

    @staticmethod
    def _side_clearance(observation: RecoveryObservation) -> tuple[float, float]:
        scan = observation.lidar[-1]
        midpoint = len(scan) // 2
        right = float(np.mean(scan[:midpoint]))
        left = float(np.mean(scan[midpoint:]))
        return left, right

    @staticmethod
    def _path_angle(observation: RecoveryObservation) -> float:
        for waypoint in observation.path_waypoints:
            if float(np.linalg.norm(waypoint)) > 1.0e-4:
                return math.atan2(float(waypoint[1]), float(waypoint[0]))
        return float(observation.goal_polar[1])

    @staticmethod
    def _front_clearance(observation: RecoveryObservation) -> float:
        """Return the nearest range in the forward 60-degree sector.

        The all-around minimum is deliberately not used here: in a narrow
        corridor a close, stationary side wall must not force repeated backup
        actions when the forward direction is clear.
        """
        scan = observation.lidar[-1]
        midpoint = len(scan) // 2
        half_width = max(1, round(len(scan) * 30.0 / 360.0))
        return float(np.min(scan[midpoint - half_width : midpoint + half_width + 1]))

    @staticmethod
    def _minimum_clearance(observation: RecoveryObservation) -> float:
        return float(np.min(observation.lidar[-1]))

    @staticmethod
    def _has_recent_progress(observation: RecoveryObservation) -> bool:
        history = observation.progress_history
        return bool(history.size >= 2 and float(history[0] - history[-1]) > 0.03)

    def _best_subgoal(
        self,
        observation: RecoveryObservation,
        mask: npt.NDArray[np.bool_],
        *,
        side: int = 0,
    ) -> int | None:
        path_angle = self._path_angle(observation)
        goal_angle = float(observation.goal_polar[1])
        scan = observation.lidar[-1]
        candidates: list[tuple[float, int]] = []
        for action in ACTIONS:
            if action.kind is not RecoveryActionKind.SUBGOAL or not bool(mask[action.action_id]):
                continue
            assert action.angle_degrees is not None and action.radius is not None
            if side:
                if action.angle_degrees == 0:
                    continue
                if int(math.copysign(1, action.angle_degrees)) != side:
                    continue
            angle = math.radians(action.angle_degrees)
            goal_progress = action.radius * math.cos(angle - goal_angle)
            if goal_progress < self.config.minimum_subgoal_progress_m:
                continue
            path_error = abs(math.atan2(math.sin(angle - path_angle), math.cos(angle - path_angle)))
            goal_error = abs(math.atan2(math.sin(angle - goal_angle), math.cos(angle - goal_angle)))
            index = round((angle + math.pi) / (2.0 * math.pi) * (len(scan) - 1))
            half_width = max(1, round(len(scan) * 6.0 / 360.0))
            start = max(0, index - half_width)
            stop = min(len(scan), index + half_width + 1)
            directional_clearance = float(np.min(scan[start:stop]))
            clearance_buffer = max(0.0, directional_clearance - action.radius)
            score = (
                self.config.path_alignment_weight * path_error
                + self.config.goal_alignment_weight * goal_error
                + self.config.radius_preference_weight
                * abs(action.radius - self.config.preferred_subgoal_radius_m)
                - self.config.progress_reward_weight * goal_progress
                - self.config.clearance_reward_weight * min(clearance_buffer, 2.0)
            )
            candidates.append((score, action.action_id))
        return min(candidates)[1] if candidates else None

    def _stable_side(self, desired: int) -> int:
        elapsed = self._decision_index - self._last_side_decision
        if (
            self._last_side != 0
            and desired != self._last_side
            and elapsed < self.config.side_cooldown_decisions
        ):
            return self._last_side
        if desired != 0 and desired != self._last_side:
            self._last_side = desired
            self._last_side_decision = self._decision_index
        return desired

    @staticmethod
    def _fallback(mask: npt.NDArray[np.bool_]) -> int:
        for action_id in (WAIT_ACTION_ID, CONTINUE_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID):
            if bool(mask[action_id]):
                return action_id
        valid = np.flatnonzero(mask)
        if valid.size == 0:
            raise ValueError("action mask contains no valid action")
        return int(valid[0])

    def select_action(
        self,
        observation: RecoveryObservation,
        action_mask: npt.NDArray[np.bool_],
    ) -> RecoveryDecision:
        mask = np.asarray(action_mask, dtype=np.bool_)
        if mask.shape != (ACTION_COUNT,):
            raise ValueError(f"action mask must have shape ({ACTION_COUNT},)")
        if not mask.any():
            raise ValueError("action mask contains no valid action")
        probabilities = observation.failure_prediction.as_array()
        dominant = FailureType(int(np.argmax(probabilities)))
        confidence = float(probabilities[dominant])
        left, right = self._side_clearance(observation)
        desired_side = 1 if left >= right else -1
        action_id: int | None = None
        reason = "fallback"

        if confidence < 0.5 and observation.planner_status in {
            PlannerStatus.ABORTED,
            PlannerStatus.NO_VALID_CONTROL,
        }:
            self._deadlock_decisions = 0
            self._collision_decisions = 0
            self._freeze_decisions = 0
            action_id = self._best_subgoal(observation, mask)
            if action_id is not None:
                reason = "planner_failure_path_subgoal"
            elif bool(mask[REPLAN_ACTION_ID]):
                action_id = REPLAN_ACTION_ID
                reason = "planner_failure_replan"
        if action_id is None and confidence < 0.5 and not self._has_recent_progress(observation):
            # A REJOIN can stall without re-triggering a high detector score.
            # Kick the local planner with a legal short subgoal instead of
            # waiting indefinitely or repeatedly resending the same goal.
            action_id = self._best_subgoal(
                observation,
                mask,
                side=self._stable_side(desired_side),
            )
            if action_id is not None:
                reason = "stalled_rejoin_side_subgoal"
            elif bool(mask[REPLAN_ACTION_ID]):
                action_id = REPLAN_ACTION_ID
                reason = "stalled_rejoin_replan"
        if action_id is None and dominant is FailureType.COLLISION_RISK:
            self._deadlock_decisions = 0
            self._collision_decisions += 1
            self._freeze_decisions = 0
            front_clearance = self._front_clearance(observation)
            minimum_clearance = self._minimum_clearance(observation)
            clearance_ratio = max(left, right) / max(1.0e-6, min(left, right))
            first_decision_wait = self._collision_decisions == 1
            if (
                first_decision_wait
                or front_clearance <= self.config.collision_emergency_wait_clearance_m
            ) and bool(mask[WAIT_ACTION_ID]):
                action_id = WAIT_ACTION_ID
                reason = "collision_imminent_wait"
            elif (
                self._collision_decisions > 1
                and (
                    front_clearance <= self.config.collision_wait_clearance_m
                    or minimum_clearance <= self.config.collision_close_clearance_m
                )
                and bool(mask[BACKUP_ACTION_ID])
            ):
                # A direct velocity override starts within the current control
                # cycle.  It is preferable to a Nav2 subgoal when a hazard is
                # still closing after the initial WAIT hold.
                action_id = BACKUP_ACTION_ID
                reason = "collision_persistent_close_backup"
            elif (
                clearance_ratio >= self.config.side_clearance_ratio or self._collision_decisions > 1
            ):
                action_id = self._best_subgoal(
                    observation, mask, side=self._stable_side(desired_side)
                )
                reason = "collision_persistent_choose_side"
            if action_id is None and self._collision_decisions > 1 and bool(mask[BACKUP_ACTION_ID]):
                action_id = BACKUP_ACTION_ID
                reason = "collision_persistent_backup"
            if action_id is None and bool(mask[WAIT_ACTION_ID]):
                action_id = WAIT_ACTION_ID
                reason = "collision_wait"
        elif action_id is None and dominant is FailureType.FREEZE:
            self._deadlock_decisions = 0
            self._collision_decisions = 0
            self._freeze_decisions += 1
            if self._freeze_decisions <= self.config.freeze_subgoal_after_decisions and bool(
                mask[BACKUP_ACTION_ID]
            ):
                action_id = BACKUP_ACTION_ID
                reason = "freeze_backup"
            else:
                front_clearance = self._front_clearance(observation)
                if front_clearance <= self.config.collision_wait_clearance_m:
                    action_id = self._best_subgoal(
                        observation,
                        mask,
                        side=self._stable_side(desired_side),
                    )
                    reason = "freeze_blocked_choose_side"
                else:
                    action_id = self._best_subgoal(observation, mask)
                    reason = "freeze_path_aligned_subgoal"
                if (
                    action_id is None
                    and self._freeze_decisions <= self.config.freeze_max_backup_decisions
                    and bool(mask[BACKUP_ACTION_ID])
                ):
                    action_id = BACKUP_ACTION_ID
                    reason = "freeze_clearance_backup"
                if action_id is None and bool(mask[REPLAN_ACTION_ID]):
                    action_id = REPLAN_ACTION_ID
                    reason = "freeze_replan"
        elif action_id is None and dominant is FailureType.OSCILLATION:
            self._deadlock_decisions = 0
            self._collision_decisions = 0
            self._freeze_decisions = 0
            side = self._stable_side(desired_side)
            action_id = self._best_subgoal(observation, mask, side=side)
            reason = "oscillation_commit_side"
        elif action_id is None and dominant is FailureType.DEADLOCK:
            self._collision_decisions = 0
            self._freeze_decisions = 0
            self._deadlock_decisions += 1
            if self._deadlock_decisions >= self.config.deadlock_replan_after_decisions and bool(
                mask[REPLAN_ACTION_ID]
            ):
                action_id = REPLAN_ACTION_ID
                reason = "deadlock_replan"
            elif self._deadlock_decisions >= self.config.deadlock_backup_after_decisions and bool(
                mask[BACKUP_ACTION_ID]
            ):
                action_id = BACKUP_ACTION_ID
                reason = "deadlock_backup"
            elif bool(mask[WAIT_ACTION_ID]):
                action_id = WAIT_ACTION_ID
                reason = "deadlock_wait"

        if action_id is None:
            action_id = self._fallback(mask)
        validate_selected_action(action_id, mask)
        self._decision_index += 1
        return RecoveryDecision(action_id, confidence, reason)
