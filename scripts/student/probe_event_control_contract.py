#!/usr/bin/env python3
"""Generate deterministic offline transition traces for an event contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "ramp_core"))

from ramp_core.scenario import (  # noqa: E402
    EventControlInput,
    EventStateMachine,
    TriggerMetric,
    event_spec_from_contract,
)


def _sample(elapsed_s: float, metric: float, trigger: TriggerMetric) -> EventControlInput:
    actor_distance = metric if trigger is TriggerMetric.ROBOT_ACTOR_DISTANCE else 99.0
    goal_distance = metric if trigger is TriggerMetric.ROBOT_GOAL_DISTANCE else 99.0
    return EventControlInput(elapsed_s, actor_distance, goal_distance)


def probe_variant(variant: dict[str, Any], split: str) -> dict[str, Any]:
    spec = event_spec_from_contract(variant, split=split)
    machine = EventStateMachine(spec)
    far = spec.trigger_threshold_m + spec.trigger_hysteresis_m + 1.0
    near = spec.trigger_threshold_m
    trigger_time = 2.0
    timeline = [
        (0.0, far),
        (1.0, far),
        (trigger_time, near),
        (trigger_time + spec.active_duration_s / 2.0, near),
        (trigger_time + spec.active_duration_s, near),
        (trigger_time + spec.active_duration_s + 1.0, far),
    ]
    trace = []
    for elapsed, metric in timeline:
        decision = machine.update(_sample(elapsed, metric, spec.trigger_metric))
        trace.append(
            {
                "elapsed_s": elapsed,
                "trigger_metric_m": metric,
                "phase": decision.phase.value,
                "command": decision.command,
                "armed": decision.armed,
                "transition": decision.transition,
                "active_elapsed_s": decision.active_elapsed_s,
            }
        )
    transitions = [item["transition"] for item in trace if item["transition"]]
    expected = ["pre_event_to_active_event", "active_event_to_released"]
    return {
        "family": variant["family"],
        "variant_id": variant["variant_id"],
        "split": split,
        "seed": int(variant[split]["seed"]),
        "spec": {
            "trigger_metric": spec.trigger_metric.value,
            "trigger_threshold_m": spec.trigger_threshold_m,
            "trigger_hysteresis_m": spec.trigger_hysteresis_m,
            "active_duration_s": spec.active_duration_s,
        },
        "trace": trace,
        "transitions": transitions,
        "valid": transitions == expected and trace[-1]["phase"] == "released",
    }


def analyze(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    traces = [
        probe_variant(variant, split)
        for variant in config["variants"]
        for split in ("train", "validation")
    ]
    source_text = (
        ROOT / "packages" / "ramp_core" / "ramp_core" / "scenario" / "events.py"
    ).read_text(encoding="utf-8")
    forbidden_imports = [
        value
        for value in ("ramp_core.observations", "ramp_core.recovery")
        if value in source_text
    ]
    return {
        "contract_id": config["contract_id"],
        "contract_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "claim_boundary": "deterministic offline traces; no ROS actor execution",
        "trace_count": len(traces),
        "all_traces_valid": all(item["valid"] for item in traces),
        "forbidden_policy_path_imports": forbidden_imports,
        "policy_observation_isolation_check": not forbidden_imports,
        "executable_scenarios_generated": False,
        "traces": traces,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.config)
    if not report["all_traces_valid"] or not report["policy_observation_isolation_check"]:
        raise SystemExit("event-control probe failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "trace_count": report["trace_count"],
                "all_traces_valid": report["all_traces_valid"],
                "policy_observation_isolation_check": report[
                    "policy_observation_isolation_check"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
