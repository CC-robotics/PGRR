"""Runtime-safe adapters for scenario events, isolated from policy inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ramp_core.scenario.events import (
    EventControlDecision,
    EventControlInput,
    EventControlSpec,
    EventStateMachine,
    TriggerMetric,
)

ADVANCE_COMMANDS = frozenset(
    {"advance_route", "resume_noncyclic_route", "release_actor_on_noncyclic_crossing"}
)
HOLD_COMMANDS = frozenset({"hold_actor_route_clock", "hold_at_start"})
TERMINAL_HOLD_COMMAND = "hold_at_off_path_terminal_waypoint"


@dataclass(frozen=True, slots=True)
class RuntimeEventDecision:
    event_id: str
    actor_name: str
    trigger_metric: str
    trigger_value_m: float
    decision: EventControlDecision


@dataclass(slots=True)
class _Binding:
    event_id: str
    actor_name: str
    machine: EventStateMachine


class ScenarioEventController:
    """Own one deterministic event machine per configured actor."""

    def __init__(self, bindings: tuple[_Binding, ...]) -> None:
        if not bindings:
            raise ValueError("event control requires at least one event")
        actor_names = [binding.actor_name for binding in bindings]
        if len(set(actor_names)) != len(actor_names):
            raise ValueError("only one event may control each actor")
        self._bindings = {binding.actor_name: binding for binding in bindings}

    @classmethod
    def from_mapping(
        cls, mapping: dict[str, Any], *, actor_names: set[str]
    ) -> ScenarioEventController:
        if int(mapping.get("schema_version", -1)) != 1:
            raise ValueError("unsupported ramp_event_control schema_version")
        raw_events = mapping.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise ValueError("ramp_event_control.events must be a non-empty list")
        bindings: list[_Binding] = []
        event_ids: set[str] = set()
        valid_commands = ADVANCE_COMMANDS | HOLD_COMMANDS | {TERMINAL_HOLD_COMMAND}
        for raw in raw_events:
            if not isinstance(raw, dict):
                raise ValueError("each event control entry must be a mapping")
            event_id = str(raw.get("event_id", "")).strip()
            actor_name = str(raw.get("actor_name", "")).strip()
            if not event_id or event_id in event_ids:
                raise ValueError("event_id must be non-empty and unique")
            if actor_name not in actor_names:
                raise ValueError(f"event actor is not present in scenario: {actor_name}")
            event_ids.add(event_id)
            commands = raw.get("commands")
            if not isinstance(commands, dict):
                raise ValueError("event commands must be a mapping")
            command_values = {
                str(commands.get("pre_event", "")),
                str(commands.get("active_event", "")),
                str(commands.get("released", "")),
            }
            unknown = command_values - valid_commands
            if unknown:
                raise ValueError(f"unsupported event commands: {sorted(unknown)}")
            spec = EventControlSpec(
                trigger_metric=TriggerMetric(str(raw.get("trigger_metric", ""))),
                trigger_threshold_m=float(raw.get("trigger_threshold_m")),
                trigger_hysteresis_m=float(raw.get("trigger_hysteresis_m")),
                active_duration_s=float(raw.get("active_duration_s")),
                pre_event_command=str(commands["pre_event"]),
                active_event_command=str(commands["active_event"]),
                released_command=str(commands["released"]),
            )
            bindings.append(
                _Binding(
                    event_id=event_id,
                    actor_name=actor_name,
                    machine=EventStateMachine(spec),
                )
            )
        return cls(tuple(bindings))

    @property
    def actor_names(self) -> frozenset[str]:
        return frozenset(self._bindings)

    def reset(self) -> None:
        for binding in self._bindings.values():
            binding.machine.reset()

    def update(
        self,
        *,
        actor_name: str,
        elapsed_s: float,
        robot_position: tuple[float, float],
        actor_position: tuple[float, float],
        goal_position: tuple[float, float],
    ) -> RuntimeEventDecision | None:
        binding = self._bindings.get(actor_name)
        if binding is None:
            return None
        robot_actor_distance = math.dist(robot_position, actor_position)
        robot_goal_distance = math.dist(robot_position, goal_position)
        decision = binding.machine.update(
            EventControlInput(
                elapsed_s=elapsed_s,
                robot_actor_distance_m=robot_actor_distance,
                robot_goal_distance_m=robot_goal_distance,
            )
        )
        trigger_value = (
            robot_actor_distance
            if binding.machine.spec.trigger_metric is TriggerMetric.ROBOT_ACTOR_DISTANCE
            else robot_goal_distance
        )
        return RuntimeEventDecision(
            event_id=binding.event_id,
            actor_name=binding.actor_name,
            trigger_metric=binding.machine.spec.trigger_metric.value,
            trigger_value_m=trigger_value,
            decision=decision,
        )


def apply_route_clock_command(
    command: str,
    *,
    current_elapsed_s: float,
    candidate_elapsed_s: float,
    terminal_elapsed_s: float,
) -> float:
    """Translate a validated event command into a route-clock target."""

    if command in ADVANCE_COMMANDS:
        return candidate_elapsed_s
    if command in HOLD_COMMANDS:
        return current_elapsed_s
    if command == TERMINAL_HOLD_COMMAND:
        return terminal_elapsed_s
    raise ValueError(f"unsupported event command: {command}")

