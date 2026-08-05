"""Failure-triggered recovery state machine with hysteresis and safety priority."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ramp_core.types import Pose2D


class RecoveryState(str, Enum):
    NORMAL = "NORMAL"
    PENDING_RECOVERY = "PENDING_RECOVERY"
    RECOVERY = "RECOVERY"
    REJOIN = "REJOIN"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class RecoveryStateMachineConfig:
    tau_on: float = 0.65
    tau_off: float = 0.35
    frames_on: int = 3
    frames_off: int = 4
    cooldown_s: float = 2.0
    minimum_action_hold_s: float = 0.5
    maximum_recovery_duration_s: float = 8.0
    maximum_extended_recovery_duration_s: float = 30.0
    maximum_recovery_sequence_duration_s: float = 45.0
    maximum_rejoin_duration_s: float = 5.0
    maximum_rejoin_retries_per_sequence: int = 2
    maximum_consecutive_recoveries: int = 4

    def __post_init__(self) -> None:
        if not 0.0 <= self.tau_off < self.tau_on <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= tau_off < tau_on <= 1")
        if self.frames_on <= 0 or self.frames_off <= 0:
            raise ValueError("hysteresis frame counts must be positive")
        if (
            min(
                self.cooldown_s,
                self.minimum_action_hold_s,
                self.maximum_recovery_duration_s,
                self.maximum_extended_recovery_duration_s,
                self.maximum_rejoin_duration_s,
            )
            < 0.0
        ):
            raise ValueError("durations must be non-negative")
        if self.maximum_extended_recovery_duration_s < self.maximum_recovery_duration_s:
            raise ValueError("extended recovery duration must cover normal recovery duration")
        if (
            not math.isfinite(self.maximum_recovery_sequence_duration_s)
            or self.maximum_recovery_sequence_duration_s <= 0.0
        ):
            raise ValueError("maximum recovery sequence duration must be finite and positive")
        if self.maximum_consecutive_recoveries <= 0:
            raise ValueError("maximum_consecutive_recoveries must be positive")
        if self.maximum_rejoin_retries_per_sequence < 0:
            raise ValueError("maximum_rejoin_retries_per_sequence must be non-negative")


@dataclass(frozen=True, slots=True)
class StateMachineInput:
    now_s: float
    failure_score: float
    valid_progress: bool
    # Short-window progress is sufficient to rejoin NORMAL, but it must not
    # erase the bounded recovery-attempt budget.  The caller raises this flag
    # only after meaningful cumulative progress toward the original goal.
    meaningful_progress: bool = False
    # The recovery manager raises this only after the nominal task goal is the
    # active planner goal again.  It prevents motion left over from a temporary
    # subgoal (or an unsuccessful restore request) from completing a sequence.
    original_goal_active: bool = False
    emergency_stop: bool = False
    goal_reached: bool = False
    unrecoverable_failure: bool = False
    recovery_action_complete: bool = False
    recovery_option_active: bool = False


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous: RecoveryState
    current: RecoveryState
    changed: bool
    reason: str


class RecoveryStateMachine:
    def __init__(self, config: RecoveryStateMachineConfig | None = None) -> None:
        self.config = config if config is not None else RecoveryStateMachineConfig()
        self.state = RecoveryState.NORMAL
        self.original_goal: Pose2D | None = None
        self._high_frames = 0
        self._low_frames = 0
        self._state_since_s = 0.0
        self._last_recovery_end_s = float("-inf")
        self._consecutive_recoveries = 0
        self._rejoin_retries = 0
        self._recovery_sequence_started_s: float | None = None
        self._original_goal_rejoined_in_sequence = False
        self._resume_after_emergency: RecoveryState | None = None

    @property
    def consecutive_recoveries(self) -> int:
        return self._consecutive_recoveries

    @property
    def state_since_s(self) -> float:
        return self._state_since_s

    def set_original_goal(self, goal: Pose2D) -> None:
        if (
            self.state in {RecoveryState.RECOVERY, RecoveryState.REJOIN}
            and self.original_goal is not None
        ):
            raise RuntimeError("cannot replace the original goal during recovery")
        self.original_goal = goal

    def reset(self, now_s: float = 0.0) -> None:
        self.state = RecoveryState.NORMAL
        self.original_goal = None
        self._high_frames = 0
        self._low_frames = 0
        self._state_since_s = now_s
        self._last_recovery_end_s = float("-inf")
        self._consecutive_recoveries = 0
        self._rejoin_retries = 0
        self._recovery_sequence_started_s = None
        self._original_goal_rejoined_in_sequence = False
        self._resume_after_emergency = None

    def _complete_recovery_sequence(self) -> None:
        """Retire the bounded sequence after confirmed nominal-goal progress."""

        self._consecutive_recoveries = 0
        self._rejoin_retries = 0
        self._recovery_sequence_started_s = None
        self._original_goal_rejoined_in_sequence = False

    def update(self, state_input: StateMachineInput) -> StateTransition:
        if not 0.0 <= state_input.failure_score <= 1.0:
            raise ValueError("failure_score must lie in [0, 1]")
        previous = self.state
        reason = "no_transition"

        if (
            self._recovery_sequence_started_s is not None
            and self.state is RecoveryState.NORMAL
            and self._original_goal_rejoined_in_sequence
            and state_input.original_goal_active
            and state_input.failure_score < self.config.tau_off
            and (state_input.valid_progress or state_input.meaningful_progress)
        ):
            # Reaching NORMAL consumed one progress observation in REJOIN.  A
            # second positive observation while the restored task goal remains
            # active confirms sustained nominal navigation and safely retires
            # the old wall-clock budget.  A momentary detector clear or an
            # emergency-stop exit cannot reach this branch.
            self._complete_recovery_sequence()
        elif (
            self._recovery_sequence_started_s is None
            and state_input.meaningful_progress
            and self.state in {RecoveryState.NORMAL, RecoveryState.PENDING_RECOVERY}
        ):
            self._consecutive_recoveries = 0
            self._rejoin_retries = 0

        if self.state in {RecoveryState.FAILED, RecoveryState.SUCCEEDED}:
            reason = "terminal_state"
        elif state_input.goal_reached:
            self.state = RecoveryState.SUCCEEDED
            reason = "goal_reached"
        elif state_input.unrecoverable_failure:
            self.state = RecoveryState.FAILED
            reason = "unrecoverable_failure"
        elif (
            self._recovery_sequence_started_s is not None
            and state_input.now_s - self._recovery_sequence_started_s
            >= self.config.maximum_recovery_sequence_duration_s
        ):
            self.state = RecoveryState.FAILED
            reason = "recovery_sequence_timeout"
        elif state_input.emergency_stop:
            if self.state is not RecoveryState.EMERGENCY_STOP:
                self._resume_after_emergency = (
                    self.state
                    if self.state
                    in {
                        RecoveryState.PENDING_RECOVERY,
                        RecoveryState.RECOVERY,
                        RecoveryState.REJOIN,
                    }
                    else None
                )
            self.state = RecoveryState.EMERGENCY_STOP
            reason = "safety_stop"
        elif self.state is RecoveryState.EMERGENCY_STOP:
            resume = self._resume_after_emergency
            self._resume_after_emergency = None
            if state_input.failure_score > self.config.tau_on and resume in {
                RecoveryState.RECOVERY,
                RecoveryState.REJOIN,
            }:
                self.state = RecoveryState.RECOVERY
                reason = "safety_clear_resume_recovery"
            elif state_input.failure_score > self.config.tau_on:
                self.state = RecoveryState.PENDING_RECOVERY
                self._high_frames = 1
                reason = "safety_clear_failure_pending"
            elif resume in {RecoveryState.RECOVERY, RecoveryState.REJOIN}:
                self.state = RecoveryState.REJOIN
                reason = "safety_clear_resume_rejoin"
            else:
                self.state = RecoveryState.NORMAL
                self._high_frames = 0
                reason = "safety_clear"
        elif self.state is RecoveryState.NORMAL:
            if state_input.failure_score > self.config.tau_on:
                self._high_frames += 1
                cooldown_elapsed = state_input.now_s - self._last_recovery_end_s
                if (
                    self._high_frames >= self.config.frames_on
                    and cooldown_elapsed >= self.config.cooldown_s
                ):
                    if self._consecutive_recoveries >= self.config.maximum_consecutive_recoveries:
                        self.state = RecoveryState.FAILED
                        reason = "recovery_limit"
                    else:
                        self.state = RecoveryState.RECOVERY
                        if self._recovery_sequence_started_s is None:
                            self._recovery_sequence_started_s = state_input.now_s
                            self._original_goal_rejoined_in_sequence = False
                        self._consecutive_recoveries += 1
                        self._rejoin_retries = 0
                        self._low_frames = 0
                        reason = "failure_confirmed"
                else:
                    self.state = RecoveryState.PENDING_RECOVERY
                    reason = "failure_pending"
            else:
                self._high_frames = 0
        elif self.state is RecoveryState.PENDING_RECOVERY:
            if state_input.failure_score > self.config.tau_on:
                self._high_frames += 1
                cooldown_elapsed = state_input.now_s - self._last_recovery_end_s
                if (
                    self._high_frames >= self.config.frames_on
                    and cooldown_elapsed >= self.config.cooldown_s
                ):
                    if self._consecutive_recoveries >= self.config.maximum_consecutive_recoveries:
                        self.state = RecoveryState.FAILED
                        reason = "recovery_limit"
                    else:
                        self.state = RecoveryState.RECOVERY
                        if self._recovery_sequence_started_s is None:
                            self._recovery_sequence_started_s = state_input.now_s
                            self._original_goal_rejoined_in_sequence = False
                        self._consecutive_recoveries += 1
                        self._rejoin_retries = 0
                        self._low_frames = 0
                        reason = "failure_confirmed"
            else:
                self.state = RecoveryState.NORMAL
                self._high_frames = 0
                reason = "failure_not_confirmed"
        elif self.state is RecoveryState.RECOVERY:
            elapsed = state_input.now_s - self._state_since_s
            recovery_limit = (
                self.config.maximum_extended_recovery_duration_s
                if state_input.recovery_option_active
                else self.config.maximum_recovery_duration_s
            )
            if elapsed >= recovery_limit:
                self.state = RecoveryState.REJOIN
                reason = "recovery_timeout"
            elif state_input.failure_score < self.config.tau_off:
                self._low_frames += 1
                if (
                    self._low_frames >= self.config.frames_off
                    and elapsed >= self.config.minimum_action_hold_s
                    and (state_input.recovery_action_complete or state_input.valid_progress)
                ):
                    self.state = RecoveryState.REJOIN
                    reason = (
                        "recovery_action_complete"
                        if state_input.recovery_action_complete
                        else "failure_cleared"
                    )
            else:
                self._low_frames = 0
        elif self.state is RecoveryState.REJOIN:
            if (
                state_input.original_goal_active
                and state_input.valid_progress
                and state_input.failure_score < self.config.tau_off
            ):
                self.state = RecoveryState.NORMAL
                self._last_recovery_end_s = state_input.now_s
                self._original_goal_rejoined_in_sequence = True
                if state_input.meaningful_progress:
                    self._complete_recovery_sequence()
                else:
                    self._rejoin_retries = 0
                self._high_frames = 0
                self._low_frames = 0
                reason = "original_goal_restored"
            elif (
                state_input.failure_score > self.config.tau_on
                or state_input.now_s - self._state_since_s >= self.config.maximum_rejoin_duration_s
            ):
                if self._rejoin_retries < self.config.maximum_rejoin_retries_per_sequence:
                    self.state = RecoveryState.RECOVERY
                    self._rejoin_retries += 1
                    self._low_frames = 0
                    reason = "rejoin_failure_retry"
                else:
                    self.state = RecoveryState.NORMAL
                    self._last_recovery_end_s = state_input.now_s
                    self._original_goal_rejoined_in_sequence = state_input.original_goal_active
                    self._high_frames = 0
                    self._low_frames = 0
                    reason = "rejoin_retry_exhausted"

        changed = self.state is not previous
        if changed:
            self._state_since_s = state_input.now_s
        return StateTransition(previous, self.state, changed, reason)
