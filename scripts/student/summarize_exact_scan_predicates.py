#!/usr/bin/env python3
"""Summarize exact original-LaserScan predicate traces for anchor diagnostics."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ramp_core.action_space import ACTIONS

STAGE = re.compile(
    r"mask_stage=observable_scan pre=([0-9,]+|none) post=([0-9,]+|none)"
)
PREDICATES = re.compile(
    r"mask_scan_predicates directional_pass=([0-9,]+|none) "
    r"capsule_pass=([0-9,]+|none) target_clearance_m=([0-9.]+) "
    r"swept_clearance_m=([0-9.]+)"
)
SUBGOALS = set(range(21))


def _ids(text: str) -> set[int]:
    return set() if text == "none" else {int(value) for value in text.split(",")}


def parse_event(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = str(row.get("recovery_reason", ""))
    stage = STAGE.search(reason)
    predicates = PREDICATES.search(reason)
    if stage is None and predicates is None:
        return None
    if stage is None or predicates is None:
        raise ValueError("scan stage and predicate trace must occur together")
    before = _ids(stage.group(1)) & SUBGOALS
    after = _ids(stage.group(2)) & SUBGOALS
    directional = _ids(predicates.group(1)) & SUBGOALS
    capsule = _ids(predicates.group(2)) & SUBGOALS
    expected = before & directional & capsule
    return {
        "before": sorted(before),
        "after": sorted(after),
        "directional_pass": sorted(directional),
        "capsule_pass": sorted(capsule),
        "expected_after": sorted(expected),
        "exact_equivalence": after == expected,
        "target_clearance_m": float(predicates.group(3)),
        "swept_clearance_m": float(predicates.group(4)),
    }


def _action_key(action_id: int) -> str:
    action = ACTIONS[action_id]
    return f"r{action.radius:.1f}_a{action.angle_degrees:+d}"


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    actions: dict[str, Counter[str]] = defaultdict(Counter)
    row_causes: Counter[str] = Counter()
    rejection_causes: Counter[str] = Counter()
    thresholds: Counter[str] = Counter()
    for event in events:
        before = set(event["before"])
        after = set(event["after"])
        directional = set(event["directional_pass"])
        capsule = set(event["capsule_pass"])
        thresholds[
            f"target={event['target_clearance_m']:.3f},swept={event['swept_clearance_m']:.3f}"
        ] += 1
        if after:
            row_causes["nonempty_intersection"] += 1
        elif not (before & directional):
            row_causes["directional_has_no_entering_action"] += 1
        elif not (before & capsule):
            row_causes["capsule_has_no_entering_action"] += 1
        else:
            row_causes["nonempty_predicates_but_disjoint_intersection"] += 1
        for action_id in sorted(before):
            directional_pass = action_id in directional
            capsule_pass = action_id in capsule
            counts = actions[_action_key(action_id)]
            counts["considered"] += 1
            counts["directional_pass"] += directional_pass
            counts["capsule_pass"] += capsule_pass
            counts["combined_pass"] += action_id in after
            if directional_pass and capsule_pass:
                rejection_causes["passed_both"] += 1
            elif directional_pass:
                rejection_causes["capsule_only_failed"] += 1
            elif capsule_pass:
                rejection_causes["directional_only_failed"] += 1
            else:
                rejection_causes["both_failed"] += 1
    return {
        "event_count": len(events),
        "exact_equivalence_count": sum(event["exact_equivalence"] for event in events),
        "all_equivalent": bool(events) and all(event["exact_equivalence"] for event in events),
        "empty_after_count": sum(not event["after"] for event in events),
        "row_cause_counts": dict(sorted(row_causes.items())),
        "action_predicate_counts": dict(sorted(rejection_causes.items())),
        "threshold_counts": dict(sorted(thresholds.items())),
        "per_action_counts": {
            key: dict(sorted(counts.items())) for key, counts in sorted(actions.items())
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
        episode_summary = summarize(events)
        if not episode_summary["all_equivalent"]:
            raise ValueError(f"predicate trace does not reproduce scan mask: {path}")
        episodes.append({"source": str(path), "summary": episode_summary})
        all_events.extend(events)
    aggregate = summarize(all_events)
    if not aggregate["all_equivalent"]:
        raise ValueError("aggregate predicate trace equivalence failed")
    return {
        "claim_boundary": "exact original-scan predicate telemetry; two train-only anchors",
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "aggregate": aggregate,
        "episodes": episodes,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    aggregate = report["aggregate"]
    row_causes = json.dumps(aggregate["row_cause_counts"], sort_keys=True)
    action_causes = json.dumps(aggregate["action_predicate_counts"], sort_keys=True)
    thresholds = json.dumps(aggregate["threshold_counts"], sort_keys=True)
    rows = []
    for key, counts in aggregate["per_action_counts"].items():
        rows.append(
            f"| {key} | {counts.get('considered', 0)} | "
            f"{counts.get('directional_pass', 0)} | {counts.get('capsule_pass', 0)} | "
            f"{counts.get('combined_pass', 0)} |"
        )
    text = f"""# Exact original-scan predicate summary

## Boundary

{report['claim_boundary']}. This is mechanism evidence, not a performance comparison.

## Aggregate

- Exact mask equivalence: {aggregate['exact_equivalence_count']}/{aggregate['event_count']}
- Empty scan-layer outputs: {aggregate['empty_after_count']}/{aggregate['event_count']}
- Empty/non-empty causes: `{row_causes}`
- Per-action predicate outcomes: `{action_causes}`
- Active clearance pairs: `{thresholds}`

| action | considered | direction pass | capsule pass | both/output pass |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

No threshold or policy was changed. Any candidate correction must be designed on
train/validation evidence and must preserve the collision-safety boundary.
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
