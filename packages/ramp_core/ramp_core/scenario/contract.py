"""Adapt validated scenario-contract mappings to event-control specifications."""

from __future__ import annotations

from typing import Any

from ramp_core.scenario.events import EventControlSpec, TriggerMetric


def event_spec_from_contract(
    variant: dict[str, Any], *, split: str
) -> EventControlSpec:
    """Build one core specification without loading files or policy objects."""

    if split not in {"train", "validation"}:
        raise ValueError("event contract split must be train or validation")
    split_config = variant.get(split)
    if not isinstance(split_config, dict):
        raise ValueError(f"event contract has no {split} mapping")
    trigger = variant.get("trigger", {})
    active = variant.get("active_event", {})
    release = variant.get("release", {})
    metric = TriggerMetric(str(trigger.get("type", "")))
    if metric is TriggerMetric.ROBOT_ACTOR_DISTANCE:
        threshold = split_config.get("trigger_distance_m", trigger.get("threshold_m"))
        duration = split_config.get("stop_duration_s", active.get("duration_s"))
        pre_command = "advance_route"
    else:
        threshold = split_config.get(
            "trigger_goal_distance_m", trigger.get("threshold_m")
        )
        duration = active.get("duration_s")
        pre_command = "hold_at_start"
    if release.get("terminal_waypoint_off_robot_centerline") is not True:
        raise ValueError("released actor must terminate off the robot centerline")
    return EventControlSpec(
        trigger_metric=metric,
        trigger_threshold_m=float(threshold),
        trigger_hysteresis_m=float(trigger.get("hysteresis_m")),
        active_duration_s=float(duration),
        pre_event_command=pre_command,
        active_event_command=str(active.get("command", "")),
        released_command=str(release.get("command", "")),
    )
