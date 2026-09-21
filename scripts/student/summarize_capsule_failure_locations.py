#!/usr/bin/env python3
"""Summarize exact swept-capsule failure locations from diagnostic traces."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

STAGE = re.compile(
    r"mask_stage=observable_scan pre=([0-9,]+|none) post=([0-9,]+|none)"
)
TRACE = re.compile(
    r"mask_scan_predicates directional_pass=([0-9,]+|none) "
    r"capsule_pass=([0-9,]+|none) target_clearance_m=([0-9.]+) "
    r"swept_clearance_m=([0-9.]+) capsule_failures=([^ ]+) "
    r"capsule_min_m=([^ ]+) capsule_fraction=([^ ;]+)"
)
MASK_TRANSITION = re.compile(r"\bpre=([0-9,]+|none)\s+(?:post|final)=([0-9,]+|none)")
SUBGOALS = set(range(21))


def _ids(text: str) -> set[int]:
    return set() if text == "none" else {int(value) for value in text.split(",")}


def _pairs(text: str) -> dict[int, float]:
    return {int(key): float(value) for item in text.split(",") for key, value in [item.split(":")]}


def _categories(text: str) -> dict[int, str]:
    if text == "none":
        return {}
    result = {}
    for group in text.split("|"):
        category, values = group.split(":", maxsplit=1)
        for action_id in _ids(values):
            result[action_id] = category
    return result


def parse_event(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = str(row.get("recovery_reason", ""))
    stage = STAGE.search(reason)
    trace = TRACE.search(reason)
    if stage is None and trace is None:
        return None
    if stage is None or trace is None:
        raise ValueError("scan stage and capsule-location trace must occur together")
    before = _ids(stage.group(1)) & SUBGOALS
    after = _ids(stage.group(2)) & SUBGOALS
    capsule_pass = _ids(trace.group(2)) & SUBGOALS
    categories = _categories(trace.group(5))
    minimums = _pairs(trace.group(6))
    fractions = _pairs(trace.group(7))
    if set(categories) != SUBGOALS - capsule_pass:
        raise ValueError("failure categories do not complement capsule pass IDs")
    if set(minimums) != SUBGOALS or set(fractions) != SUBGOALS:
        raise ValueError("capsule distance/fraction telemetry must cover all subgoals")
    transitions = [MASK_TRANSITION.search(segment) for segment in reason.split(";")]
    parsed_transitions = [match for match in transitions if match is not None]
    if not parsed_transitions:
        raise ValueError("no final action-mask transition is available")
    final_actions = _ids(parsed_transitions[-1].group(2))
    return {
        "before": sorted(before),
        "after": sorted(after),
        "capsule_pass": sorted(capsule_pass),
        "categories": categories,
        "minimums_m": minimums,
        "fractions": fractions,
        "swept_clearance_m": float(trace.group(4)),
        "selected_action": int(row.get("recovery_action", 24)),
        "final_actions": sorted(final_actions),
    }


def _distance_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "minimum_m": ordered[0],
        "median_m": median(ordered),
        "maximum_m": ordered[-1],
    }


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    category_actions: Counter[str] = Counter()
    empty_category_actions: Counter[str] = Counter()
    category_events: Counter[str] = Counter()
    distances: dict[str, list[float]] = defaultdict(list)
    deficits: dict[str, list[float]] = defaultdict(list)
    selected_actions: Counter[str] = Counter()
    nonempty_selected_actions: Counter[str] = Counter()
    scan_nonempty_final_empty = 0
    scan_nonempty_final_nonempty = 0
    final_nonempty_selected_temporary = 0
    for event in events:
        selected_actions[str(event["selected_action"])] += 1
        if event["after"]:
            nonempty_selected_actions[str(event["selected_action"])] += 1
            final_temporary = set(event["final_actions"]) & SUBGOALS
            if final_temporary:
                scan_nonempty_final_nonempty += 1
                final_nonempty_selected_temporary += event["selected_action"] < 21
            else:
                scan_nonempty_final_empty += 1
        present = set()
        before = set(event["before"])
        for action_id, category in event["categories"].items():
            if action_id not in before:
                continue
            present.add(category)
            category_actions[category] += 1
            if not event["after"]:
                empty_category_actions[category] += 1
            distance = float(event["minimums_m"][action_id])
            distances[category].append(distance)
            deficits[category].append(event["swept_clearance_m"] - distance)
        category_events.update(present)
    return {
        "event_count": len(events),
        "empty_after_count": sum(not event["after"] for event in events),
        "category_action_counts": dict(sorted(category_actions.items())),
        "empty_event_category_action_counts": dict(sorted(empty_category_actions.items())),
        "category_event_presence_counts": dict(sorted(category_events.items())),
        "selected_action_counts": dict(sorted(selected_actions.items())),
        "nonempty_scan_selected_action_counts": dict(sorted(nonempty_selected_actions.items())),
        "nonempty_scan_selected_temporary_count": sum(
            bool(event["after"]) and event["selected_action"] < 21 for event in events
        ),
        "scan_nonempty_final_temporary_empty_count": scan_nonempty_final_empty,
        "scan_nonempty_final_temporary_nonempty_count": scan_nonempty_final_nonempty,
        "final_temporary_nonempty_selected_temporary_count": final_nonempty_selected_temporary,
        "minimum_clearance_by_category": {
            category: _distance_summary(values) for category, values in sorted(distances.items())
        },
        "clearance_deficit_by_category": {
            category: _distance_summary(values) for category, values in sorted(deficits.items())
        },
    }


def analyze(paths: list[Path]) -> dict[str, Any]:
    episodes = []
    all_events = []
    for path in paths:
        events = []
        with path.open(encoding="utf-8") as stream:
            for sample_index, line in enumerate(stream):
                if not line.strip():
                    continue
                event = parse_event(json.loads(line))
                if event is not None:
                    event["sample_index"] = sample_index
                    events.append(event)
        episodes.append({"source": str(path), "summary": summarize(events)})
        all_events.extend(events)
    return {
        "claim_boundary": (
            "exact runtime failure categories and original-scan distances rounded to 0.001 m; "
            "two train-only anchors"
        ),
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "aggregate": summarize(all_events),
        "episodes": episodes,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    aggregate = report["aggregate"]
    categories = json.dumps(aggregate["category_action_counts"], sort_keys=True)
    empty_categories = json.dumps(
        aggregate["empty_event_category_action_counts"], sort_keys=True
    )
    presence = json.dumps(aggregate["category_event_presence_counts"], sort_keys=True)
    distances = json.dumps(aggregate["minimum_clearance_by_category"], sort_keys=True)
    deficits = json.dumps(aggregate["clearance_deficit_by_category"], sort_keys=True)
    selected = json.dumps(aggregate["selected_action_counts"], sort_keys=True)
    selected_nonempty = json.dumps(
        aggregate["nonempty_scan_selected_action_counts"], sort_keys=True
    )
    selected_temporary = aggregate["nonempty_scan_selected_temporary_count"]
    downstream_empty = aggregate["scan_nonempty_final_temporary_empty_count"]
    downstream_nonempty = aggregate["scan_nonempty_final_temporary_nonempty_count"]
    final_selected_temporary = aggregate["final_temporary_nonempty_selected_temporary_count"]
    text = f"""# Swept-capsule failure-location summary

## Boundary

{report['claim_boundary']}. This does not authorize a threshold change.

## Results

- Trace decisions: {aggregate['event_count']}
- Empty scan outputs: {aggregate['empty_after_count']}
- Failed action instances by category: `{categories}`
- Failed action instances inside empty decisions: `{empty_categories}`
- Decisions containing each category: `{presence}`
- Minimum segment clearance by category: `{distances}`
- Clearance deficit by category: `{deficits}`
- Selected actions: `{selected}`
- Selected actions when scan retained a temporary candidate: `{selected_nonempty}`
- Temporary actions selected when scan was nonempty: {selected_temporary}
- Scan nonempty but final temporary mask empty: {downstream_empty}
- Scan and final temporary masks both nonempty: {downstream_nonempty}
- Temporary selections when final temporary mask was nonempty: {final_selected_temporary}

The next design step must distinguish trajectory-shape limitations from clearance
selection. Endpoint/interior failures cannot be treated as harmless initial overlap.
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
