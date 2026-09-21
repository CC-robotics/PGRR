from __future__ import annotations

import pytest
from ramp_core.scenario import ScenarioEventController, apply_route_clock_command


def _mapping() -> dict[str, object]:
    return {
        "schema_version": 1,
        "events": [
            {
                "event_id": "lead_stop",
                "actor_name": "person_1",
                "trigger_metric": "robot_actor_distance_below",
                "trigger_threshold_m": 3.0,
                "trigger_hysteresis_m": 0.25,
                "active_duration_s": 3.0,
                "commands": {
                    "pre_event": "advance_route",
                    "active_event": "hold_actor_route_clock",
                    "released": "resume_noncyclic_route",
                },
            }
        ],
    }


def test_controller_uses_geometry_and_reset_without_policy_state() -> None:
    controller = ScenarioEventController.from_mapping(
        _mapping(), actor_names={"person_1"}
    )
    armed = controller.update(
        actor_name="person_1",
        elapsed_s=0.0,
        robot_position=(0.0, 0.0),
        actor_position=(4.0, 0.0),
        goal_position=(10.0, 0.0),
    )
    assert armed is not None and armed.decision.armed
    active = controller.update(
        actor_name="person_1",
        elapsed_s=1.0,
        robot_position=(1.5, 0.0),
        actor_position=(4.0, 0.0),
        goal_position=(10.0, 0.0),
    )
    assert active is not None
    assert active.decision.transition == "pre_event_to_active_event"
    assert active.trigger_value_m == pytest.approx(2.5)
    controller.reset()
    reset = controller.update(
        actor_name="person_1",
        elapsed_s=0.0,
        robot_position=(0.0, 0.0),
        actor_position=(4.0, 0.0),
        goal_position=(10.0, 0.0),
    )
    assert reset is not None and reset.decision.phase.value == "pre_event"


def test_controller_rejects_unknown_actor_and_duplicate_binding() -> None:
    with pytest.raises(ValueError, match="not present"):
        ScenarioEventController.from_mapping(_mapping(), actor_names={"person_2"})
    duplicate = _mapping()
    duplicate["events"] = [*duplicate["events"], dict(duplicate["events"][0])]
    duplicate["events"][1]["event_id"] = "other"
    with pytest.raises(ValueError, match="one event"):
        ScenarioEventController.from_mapping(duplicate, actor_names={"person_1"})


def test_route_clock_commands_are_explicit_and_fail_closed() -> None:
    values = {
        "current_elapsed_s": 2.0,
        "candidate_elapsed_s": 2.5,
        "terminal_elapsed_s": 10.0,
    }
    assert apply_route_clock_command("advance_route", **values) == 2.5
    assert apply_route_clock_command("hold_actor_route_clock", **values) == 2.0
    assert apply_route_clock_command("hold_at_off_path_terminal_waypoint", **values) == 10.0
    with pytest.raises(ValueError, match="unsupported"):
        apply_route_clock_command("teleport_to_goal", **values)

