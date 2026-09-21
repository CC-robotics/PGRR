from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_actor_wiring_is_default_off_resettable_and_freshness_gated() -> None:
    actor = _source(
        "ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py"
    )
    assert 'declare_parameter("enable_event_control", False)' in actor
    assert 'declare_parameter("scenario_event_topic", "/ramp/scenario_events")' in actor
    assert 'scenario.get("ramp_event_control")' in actor
    assert "if not enabled:" in actor
    assert "self._event_controller.reset()" in actor
    assert "not self._actual_robot_pose_is_fresh(now_s)" in actor
    assert "now_s - pose_received_s > timeout_s" in actor
    assert "return current_elapsed_s" in actor
    assert "apply_route_clock_command(" in actor
    reset = actor[actor.index("def _on_task_reset") : actor.index("def _on_logger_ready")]
    assert reset.index("self._event_start_s = None") < reset.index(
        "self._event_controller.reset()"
    )


def test_event_telemetry_is_outcome_only_and_not_a_policy_observation() -> None:
    actor = _source(
        "ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py"
    )
    logger = _source("ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py")
    recovery = _source("ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py")
    assert "self._event_publisher.publish(message)" in actor
    assert "def _on_scenario_event" in logger
    assert '"scenario_events": self._scenario_events' in logger
    assert "maximum_scenario_event_transitions" in logger
    assert "scenario_event_topic" not in recovery


def test_launchers_forward_one_validated_opt_in_flag() -> None:
    wrapper = _source("scripts/arena/run_baseline_episode.sh")
    runtime = _source("scripts/arena/run_baseline_episode_inner.sh")
    assert 'event_control="${RAMP_ENABLE_EVENT_CONTROL:-0}"' in wrapper
    assert "RAMP_ENABLE_EVENT_CONTROL must be 0 or 1" in wrapper
    assert 'optional_runtime_environment+=("RAMP_ENABLE_EVENT_CONTROL=${event_control}")' in wrapper
    assert 'ENABLE_EVENT_CONTROL="${RAMP_ENABLE_EVENT_CONTROL:-0}"' in runtime
    assert '-p enable_event_control:="${event_control_ros_value}"' in runtime
    assert runtime.count("scenario_event_topic:=/ramp/scenario_events") == 2
    assert '-p goal_x:="${goal_x}" -p goal_y:="${goal_y}"' in runtime

