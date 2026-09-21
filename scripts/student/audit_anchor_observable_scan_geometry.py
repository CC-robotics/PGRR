#!/usr/bin/env python3
"""Audit exact logged observable-scan removals and approximate geometric causes."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.action_space import ACTIONS
from ramp_core.planning.online import directional_scan_clearance, scan_segment_is_free
from ramp_core.recovery.safety import collision_latched_motion_clearance

TRANSITION = re.compile(
    r"mask_stage=(map_connectivity|observable_scan|path_corridor) "
    r"pre=([0-9,]+|none) post=([0-9,]+|none)"
)
FORWARD_CLEARANCE = re.compile(r"forward_clearance_m=([0-9.]+)")
SUBGOAL_IDS = set(range(21))
ANGLE_MIN = math.radians(-135.0)
ANGLE_INCREMENT = math.radians(270.0) / 179.0
SECTOR_HALF_WIDTH = math.radians(12.0)


def _ids(text: str) -> set[int]:
    return set() if text == "none" else {int(item) for item in text.split(",")}


def parse_transitions(reason: str) -> dict[str, tuple[set[int], set[int]]]:
    return {
        stage: (_ids(before), _ids(after)) for stage, before, after in TRANSITION.findall(reason)
    }


def _approximate_predicates(lidar: list[float], collision_risk: float) -> dict[int, dict[str, Any]]:
    action_clearance = 0.25
    swept_clearance = 0.48
    latched = collision_risk >= 0.65
    if latched:
        action_clearance = collision_latched_motion_clearance(
            configured_action_clearance_m=0.90,
            stop_clearance_m=0.85,
            release_hysteresis_m=0.05,
        )
        swept_clearance = max(swept_clearance, action_clearance)
    ranges = np.asarray(lidar, dtype=np.float64)
    result: dict[int, dict[str, Any]] = {}
    for action in ACTIONS[:21]:
        assert action.radius is not None and action.angle_degrees is not None
        direction = math.radians(action.angle_degrees)
        clearance = directional_scan_clearance(
            ranges,
            angle_min=ANGLE_MIN,
            angle_increment=ANGLE_INCREMENT,
            direction=direction,
            half_width_rad=SECTOR_HALF_WIDTH,
        )
        directional_pass = bool(
            clearance is not None and clearance >= action.radius + action_clearance
        )
        capsule_pass = scan_segment_is_free(
            ranges,
            angle_min=ANGLE_MIN,
            angle_increment=ANGLE_INCREMENT,
            target=(
                action.radius * math.cos(direction),
                action.radius * math.sin(direction),
            ),
            clearance_m=swept_clearance,
            allow_initial_overlap_when_separating=latched,
        )
        result[action.action_id] = {
            "directional_clearance_m": clearance,
            "directional_threshold_m": action.radius + action_clearance,
            "directional_pass": directional_pass,
            "capsule_pass": capsule_pass,
            "combined_pass": directional_pass and capsule_pass,
        }
    return result


def analyze_row(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = str(row.get("recovery_reason", ""))
    transitions = parse_transitions(reason)
    if "observable_scan" not in transitions:
        return None
    before, after = transitions["observable_scan"]
    considered = before & SUBGOAL_IDS
    retained = after & SUBGOAL_IDS
    collision_risk = float(row["failure_prediction"][0])
    predicates = _approximate_predicates(row["lidar"], collision_risk)
    approximate_retained = {
        action_id for action_id in considered if predicates[action_id]["combined_pass"]
    }
    forward_match = FORWARD_CLEARANCE.search(reason)
    return {
        "considered": sorted(considered),
        "retained": sorted(retained),
        "removed": sorted(considered - retained),
        "approximate_retained": sorted(approximate_retained),
        "approximate_exact_match": approximate_retained == retained,
        "approximate_false_retained": sorted(approximate_retained - retained),
        "approximate_false_removed": sorted(retained - approximate_retained),
        "collision_risk": collision_risk,
        "collision_latched": collision_risk >= 0.65,
        "forward_clearance_m": float(forward_match.group(1)) if forward_match else None,
        "predicates": predicates,
    }


def _action_key(action_id: int) -> str:
    action = ACTIONS[action_id]
    return f"r{action.radius:.1f}_a{action.angle_degrees:+d}"


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts: dict[str, Counter[str]] = defaultdict(Counter)
    radius_counts: dict[str, Counter[str]] = defaultdict(Counter)
    angle_counts: dict[str, Counter[str]] = defaultdict(Counter)
    cause_counts: Counter[str] = Counter()
    retained_masks: Counter[str] = Counter()
    latch_empty_counts: Counter[str] = Counter()
    exact_actions = 0
    matching_actions = 0
    all_empty_with_large_forward = 0
    for event in events:
        retained = set(event["retained"])
        considered = set(event["considered"])
        approximate = set(event["approximate_retained"])
        retained_masks[",".join(map(str, sorted(retained))) or "none"] += 1
        latch_name = "latched" if event["collision_latched"] else "not_latched"
        latch_empty_counts[f"{latch_name}:decisions"] += 1
        latch_empty_counts[f"{latch_name}:empty"] += not retained
        for action_id in sorted(considered):
            action = ACTIONS[action_id]
            assert action.radius is not None and action.angle_degrees is not None
            counts = action_counts[_action_key(action_id)]
            counts["considered"] += 1
            counts["retained"] += action_id in retained
            counts["removed"] += action_id not in retained
            for grouped in (
                radius_counts[f"{action.radius:.1f}m"],
                angle_counts[f"{action.angle_degrees:+d}deg"],
            ):
                grouped["considered"] += 1
                grouped["retained"] += action_id in retained
                grouped["removed"] += action_id not in retained
            matching_actions += (action_id in retained) == (action_id in approximate)
            exact_actions += 1
            predicate = event["predicates"][action_id]
            if not predicate["directional_pass"] and not predicate["capsule_pass"]:
                cause_counts["approx_both_failed"] += 1
            elif not predicate["directional_pass"]:
                cause_counts["approx_directional_only_failed"] += 1
            elif not predicate["capsule_pass"]:
                cause_counts["approx_capsule_only_failed"] += 1
            else:
                cause_counts["approx_both_passed"] += 1
        if (
            considered
            and not retained
            and event["forward_clearance_m"] is not None
            and event["forward_clearance_m"] >= 1.5
        ):
            all_empty_with_large_forward += 1
    return {
        "decision_count": len(events),
        "collision_latched_decision_count": sum(event["collision_latched"] for event in events),
        "all_temporary_empty_count": sum(not event["retained"] for event in events),
        "forward_clearance_observed_count": sum(
            event["forward_clearance_m"] is not None for event in events
        ),
        "all_empty_with_forward_clearance_at_least_1_5m_count": all_empty_with_large_forward,
        "approximate_exact_decision_match_count": sum(
            event["approximate_exact_match"] for event in events
        ),
        "approximate_exact_decision_match_rate": (
            sum(event["approximate_exact_match"] for event in events) / len(events)
            if events
            else None
        ),
        "approximate_action_classification_match_rate": (
            matching_actions / exact_actions if exact_actions else None
        ),
        "exact_logged_action_counts": {
            key: dict(sorted(counts.items())) for key, counts in sorted(action_counts.items())
        },
        "exact_logged_radius_counts": {
            key: dict(sorted(counts.items())) for key, counts in sorted(radius_counts.items())
        },
        "exact_logged_angle_counts": {
            key: dict(sorted(counts.items())) for key, counts in sorted(angle_counts.items())
        },
        "exact_logged_retained_mask_counts": dict(sorted(retained_masks.items())),
        "exact_logged_latch_empty_counts": dict(sorted(latch_empty_counts.items())),
        "approximate_predicate_counts": dict(sorted(cause_counts.items())),
    }


def analyze(files: list[Path]) -> dict[str, Any]:
    episodes = []
    all_events = []
    for path in files:
        events = []
        with path.open(encoding="utf-8") as stream:
            for sample_index, line in enumerate(stream):
                if not line.strip():
                    continue
                event = analyze_row(json.loads(line))
                if event is None:
                    continue
                event["sample_index"] = sample_index
                events.append(event)
        episodes.append({"source": str(path), "summary": _summarize_events(events)})
        all_events.extend(events)
    return {
        "claim_boundary": (
            "Logged pre/post removals are exact. Predicate decomposition is an approximate "
            "replay from 180-beam resampled telemetry, not the original runtime LaserScan."
        ),
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "scan_replay_assumptions": {
            "field_of_view_degrees": 270.0,
            "beam_count": 180,
            "normal_target_clearance_m": 0.25,
            "normal_swept_clearance_m": 0.48,
            "collision_latched_clearance_m": 0.90,
            "collision_latch_threshold": 0.65,
            "sector_half_width_degrees": 12.0,
        },
        "aggregate": _summarize_events(all_events),
        "episodes": episodes,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    aggregate = report["aggregate"]
    empty_count = aggregate["all_temporary_empty_count"]
    forward_count = aggregate["forward_clearance_observed_count"]
    large_forward_empty = aggregate["all_empty_with_forward_clearance_at_least_1_5m_count"]
    latch_counts = json.dumps(aggregate["exact_logged_latch_empty_counts"], sort_keys=True)
    mask_counts = json.dumps(aggregate["exact_logged_retained_mask_counts"], sort_keys=True)
    radius_counts = json.dumps(aggregate["exact_logged_radius_counts"], sort_keys=True)
    angle_counts = json.dumps(aggregate["exact_logged_angle_counts"], sort_keys=True)
    decision_match = aggregate["approximate_exact_decision_match_rate"]
    action_match = aggregate["approximate_action_classification_match_rate"]
    predicate_counts = json.dumps(aggregate["approximate_predicate_counts"], sort_keys=True)
    rows = []
    for key, counts in aggregate["exact_logged_action_counts"].items():
        rows.append(
            f"| {key} | {counts.get('considered', 0)} | {counts.get('retained', 0)} | "
            f"{counts.get('removed', 0)} |"
        )
    text = f"""# Two-anchor observable-scan geometry audit

## Boundary

{report["claim_boundary"]}

## Exact logged findings

- Decisions: {aggregate["decision_count"]}
- Collision-latched decisions: {aggregate["collision_latched_decision_count"]}
- Decisions with no temporary subgoal after observable scan: {empty_count}
- Decisions exposing forward-clearance telemetry: {forward_count}
- Empty despite logged forward clearance >= 1.5 m: {large_forward_empty}
- Empty/non-empty by collision latch: `{latch_counts}`
- Retained-mask patterns: `{mask_counts}`
- Radius totals: `{radius_counts}`
- Angle totals: `{angle_counts}`

| action (radius, angle) | considered | retained | removed |
|---|---:|---:|---:|
{chr(10).join(rows)}

## Approximate predicate replay

- Exact whole-decision match rate: {decision_match:.3f}
- Per-action classification match rate: {action_match:.3f}
- Predicate counts: `{predicate_counts}`

The approximation is useful only if its reported agreement is adequate. It must not be
used to relax a safety clearance, retrain a model, or claim causal failure without a new
runtime trace that records the original scan or the two predicate outcomes directly.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, action="append", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.jsonl)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(report, args.markdown_output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
