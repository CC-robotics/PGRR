"""Deterministic one-shot scenario events with bounded release.

This module controls simulator actors only. Its values are deliberately not part
of the recovery-policy observation schema.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class EventPhase(str, Enum):
    PRE_EVENT = "pre_event"
    ACTIVE_EVENT = "active_event"
    RELEASED = "released"


class TriggerMetric(str, Enum):
    ROBOT_ACTOR_DISTANCE = "robot_actor_distance_below"
    ROBOT_GOAL_DISTANCE = "robot_goal_distance_below"


@dataclass(frozen=True, slots=True)
class EventControlSpec:
    trigger_metric: TriggerMetric
    trigger_threshold_m: float
    trigger_hysteresis_m: float
    active_duration_s: float
    pre_event_command: str
    active_event_command: str
    released_command: str

    def __post_init__(self) -> None:
        values = (
            self.trigger_threshold_m,
            self.trigger_hysteresis_m,
            self.active_duration_s,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("event thresholds and duration must be finite")
        if self.trigger_threshold_m <= 0.0:
            raise ValueError("trigger threshold must be positive")
        if self.trigger_hysteresis_m < 0.0:
            raise ValueError("trigger hysteresis must be non-negative")
        if self.active_duration_s <= 0.0:
            raise ValueError("active duration must be positive")
        commands = (
            self.pre_event_command,
            self.active_event_command,
            self.released_command,
        )
        if any(not command.strip() for command in commands):
            raise ValueError("event commands must not be empty")


@dataclass(frozen=True, slots=True)
class EventControlInput:
    elapsed_s: float
    robot_actor_distance_m: float
    robot_goal_distance_m: float

    def __post_init__(self) -> None:
        values = (
            self.elapsed_s,
            self.robot_actor_distance_m,
            self.robot_goal_distance_m,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("event-control input must be finite")
        if any(value < 0.0 for value in values):
            raise ValueError("event-control input must be non-negative")


@dataclass(frozen=True, slots=True)
class EventControlDecision:
    phase: EventPhase
    command: str
    armed: bool
    transitioned: bool
    transition: str | None
    trigger_elapsed_s: float | None
    active_elapsed_s: float


class EventStateMachine:
    """One-shot three-phase event controller with explicit reset and arming.

    Arming requires first observing the trigger metric above threshold plus
    hysteresis. This prevents an invalid initial placement from silently starting
    the event at reset. Once triggered, the event cannot retrigger.
    """

    def __init__(self, spec: EventControlSpec) -> None:
        self.spec = spec
        self.reset()

    def reset(self) -> None:
        self._phase = EventPhase.PRE_EVENT
        self._armed = False
        self._trigger_elapsed_s: float | None = None
        self._last_elapsed_s: float | None = None

    def _metric(self, state: EventControlInput) -> float:
        if self.spec.trigger_metric is TriggerMetric.ROBOT_ACTOR_DISTANCE:
            return state.robot_actor_distance_m
        return state.robot_goal_distance_m

    def _command(self) -> str:
        if self._phase is EventPhase.PRE_EVENT:
            return self.spec.pre_event_command
        if self._phase is EventPhase.ACTIVE_EVENT:
            return self.spec.active_event_command
        return self.spec.released_command

    def update(self, state: EventControlInput) -> EventControlDecision:
        if self._last_elapsed_s is not None and state.elapsed_s < self._last_elapsed_s:
            raise ValueError("event elapsed time must be monotonic")
        self._last_elapsed_s = state.elapsed_s
        transitioned = False
        transition = None
        metric = self._metric(state)
        if self._phase is EventPhase.PRE_EVENT:
            arm_threshold = (
                self.spec.trigger_threshold_m + self.spec.trigger_hysteresis_m
            )
            if metric > arm_threshold:
                self._armed = True
            if self._armed and metric <= self.spec.trigger_threshold_m:
                self._phase = EventPhase.ACTIVE_EVENT
                self._trigger_elapsed_s = state.elapsed_s
                transitioned = True
                transition = "pre_event_to_active_event"
        elif self._phase is EventPhase.ACTIVE_EVENT:
            assert self._trigger_elapsed_s is not None
            if state.elapsed_s - self._trigger_elapsed_s >= self.spec.active_duration_s:
                self._phase = EventPhase.RELEASED
                transitioned = True
                transition = "active_event_to_released"
        active_elapsed_s = 0.0
        if self._trigger_elapsed_s is not None:
            active_elapsed_s = min(
                max(0.0, state.elapsed_s - self._trigger_elapsed_s),
                self.spec.active_duration_s,
            )
        return EventControlDecision(
            phase=self._phase,
            command=self._command(),
            armed=self._armed,
            transitioned=transitioned,
            transition=transition,
            trigger_elapsed_s=self._trigger_elapsed_s,
            active_elapsed_s=active_elapsed_s,
        )
