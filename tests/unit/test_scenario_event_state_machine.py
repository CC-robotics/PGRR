from __future__ import annotations

import pytest
from ramp_core.scenario.events import (
    EventControlInput,
    EventControlSpec,
    EventPhase,
    EventStateMachine,
    TriggerMetric,
)


def _spec(metric: TriggerMetric = TriggerMetric.ROBOT_ACTOR_DISTANCE) -> EventControlSpec:
    return EventControlSpec(
        trigger_metric=metric,
        trigger_threshold_m=3.0,
        trigger_hysteresis_m=0.25,
        active_duration_s=3.0,
        pre_event_command="advance_route",
        active_event_command="hold_route_clock",
        released_command="resume_route",
    )


def _input(elapsed: float, actor: float, goal: float = 20.0) -> EventControlInput:
    return EventControlInput(elapsed, actor, goal)


def test_actor_distance_event_arms_triggers_holds_and_releases_once() -> None:
    machine = EventStateMachine(_spec())
    assert machine.update(_input(0.0, 4.0)).phase is EventPhase.PRE_EVENT
    triggered = machine.update(_input(1.0, 3.0))
    assert triggered.phase is EventPhase.ACTIVE_EVENT
    assert triggered.transition == "pre_event_to_active_event"
    assert triggered.command == "hold_route_clock"
    active = machine.update(_input(3.9, 2.0))
    assert active.phase is EventPhase.ACTIVE_EVENT
    assert active.active_elapsed_s == pytest.approx(2.9)
    released = machine.update(_input(4.0, 2.0))
    assert released.phase is EventPhase.RELEASED
    assert released.transition == "active_event_to_released"
    assert released.command == "resume_route"
    still_released = machine.update(_input(8.0, 4.0))
    assert still_released.phase is EventPhase.RELEASED
    assert still_released.transitioned is False


def test_goal_distance_metric_does_not_use_actor_distance() -> None:
    machine = EventStateMachine(_spec(TriggerMetric.ROBOT_GOAL_DISTANCE))
    machine.update(_input(0.0, 0.1, goal=6.0))
    decision = machine.update(_input(1.0, 100.0, goal=3.0))
    assert decision.phase is EventPhase.ACTIVE_EVENT


def test_invalid_initial_proximity_does_not_silently_trigger() -> None:
    machine = EventStateMachine(_spec())
    decision = machine.update(_input(0.0, 2.0))
    assert decision.phase is EventPhase.PRE_EVENT
    assert decision.armed is False


def test_reset_requires_new_arming_crossing() -> None:
    machine = EventStateMachine(_spec())
    machine.update(_input(0.0, 4.0))
    machine.update(_input(1.0, 2.0))
    machine.reset()
    decision = machine.update(_input(0.0, 2.0))
    assert decision.phase is EventPhase.PRE_EVENT
    assert decision.trigger_elapsed_s is None


def test_elapsed_time_must_be_monotonic() -> None:
    machine = EventStateMachine(_spec())
    machine.update(_input(2.0, 4.0))
    with pytest.raises(ValueError, match="monotonic"):
        machine.update(_input(1.0, 3.0))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trigger_threshold_m", 0.0),
        ("trigger_hysteresis_m", -0.1),
        ("active_duration_s", 0.0),
    ],
)
def test_invalid_spec_values_are_rejected(field: str, value: float) -> None:
    values = {
        "trigger_metric": TriggerMetric.ROBOT_ACTOR_DISTANCE,
        "trigger_threshold_m": 3.0,
        "trigger_hysteresis_m": 0.25,
        "active_duration_s": 3.0,
        "pre_event_command": "advance",
        "active_event_command": "hold",
        "released_command": "resume",
    }
    values[field] = value
    with pytest.raises(ValueError):
        EventControlSpec(**values)
