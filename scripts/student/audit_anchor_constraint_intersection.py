#!/usr/bin/env python3
"""Audit which exact constraint removes scan-surviving anchor subgoals."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCAN_STAGE = re.compile(
    r"mask_stage=observable_scan pre=([0-9,]+|none) post=([0-9,]+|none)"
)
TRANSITION = re.compile(r"\bpre=([0-9,]+|none)\s+(?:post|final)=([0-9,]+|none)")
SUBGOALS = set(range(21))
RADII = (0.6, 1.0, 1.4)
ANGLES = (-90, -60, -30, 0, 30, 60, 90)


def _ids(text: str) -> set[int]:
    return set() if text == "none" else {int(value) for value in text.split(",")}


def action_geometry(action_id: int) -> dict[str, float | int]:
    if action_id not in SUBGOALS:
        raise ValueError("action must be a temporary-subgoal ID")
    return {
        "action_id": action_id,
        "radius_m": RADII[action_id // len(ANGLES)],
        "angle_deg": ANGLES[action_id % len(ANGLES)],
    }


def parse_event(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = str(row.get("recovery_reason", ""))
    scan_match = SCAN_STAGE.search(reason)
    if scan_match is None:
        return None
    scan_pre = _ids(scan_match.group(1)) & SUBGOALS
    scan_post = _ids(scan_match.group(2)) & SUBGOALS
    scan_end = scan_match.end()
    downstream = []
    current = set(scan_post)
    first_empty_constraint = "observable_scan" if scan_pre and not scan_post else None
    for segment in reason[scan_end:].split(";"):
        match = TRANSITION.search(segment)
        if match is None:
            continue
        label = segment.strip().split(maxsplit=1)[0].split("=", maxsplit=1)[0]
        before = _ids(match.group(1)) & SUBGOALS
        after = _ids(match.group(2)) & SUBGOALS
        # Non-subgoal rejoin constraints may create an intentional telemetry gap.
        # Only require continuity for the surviving temporary-subgoal subset.
        if before != current:
            raise ValueError(
                "temporary-mask discontinuity before "
                f"{label}: {sorted(current)} != {sorted(before)}"
            )
        removed = current - after
        downstream.append(
            {
                "constraint": label,
                "pre": sorted(before),
                "post": sorted(after),
                "removed": sorted(removed),
            }
        )
        if current and not after and first_empty_constraint is None:
            first_empty_constraint = label
        current = after
    return {
        "scan_pre": sorted(scan_pre),
        "scan_post": sorted(scan_post),
        "downstream": downstream,
        "final_temporary": sorted(current),
        "first_empty_constraint": first_empty_constraint,
        "selected_action": int(row.get("recovery_action", 24)),
    }


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    first_empty = Counter(event["first_empty_constraint"] or "NOT_EMPTY" for event in events)
    scan_survivors: Counter[str] = Counter()
    removed_by: defaultdict[str, Counter[str]] = defaultdict(Counter)
    scan_nonempty_events = 0
    for event in events:
        if event["scan_post"]:
            scan_nonempty_events += 1
            scan_survivors.update(str(action_id) for action_id in event["scan_post"])
        for step in event["downstream"]:
            if step["removed"]:
                removed_by[step["constraint"]].update(
                    str(action_id) for action_id in step["removed"]
                )
    geometry = {
        action_id: action_geometry(int(action_id)) for action_id in sorted(scan_survivors, key=int)
    }
    return {
        "event_count": len(events),
        "scan_empty_count": sum(not event["scan_post"] for event in events),
        "scan_nonempty_count": scan_nonempty_events,
        "final_temporary_empty_count": sum(not event["final_temporary"] for event in events),
        "first_empty_constraint_counts": dict(sorted(first_empty.items())),
        "scan_survivor_action_occurrences": dict(
            sorted(scan_survivors.items(), key=lambda x: int(x[0]))
        ),
        "scan_survivor_geometry": geometry,
        "removed_action_occurrences_by_downstream_constraint": {
            name: dict(sorted(values.items(), key=lambda x: int(x[0])))
            for name, values in sorted(removed_by.items())
        },
        "temporary_action_selected_count": sum(event["selected_action"] < 21 for event in events),
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
        "claim_boundary": "exact logged mask intersections from two train-only anchors",
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "aggregate": summarize(all_events),
        "episodes": episodes,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["aggregate"]
    first_empty = json.dumps(summary["first_empty_constraint_counts"], sort_keys=True)
    survivors = json.dumps(summary["scan_survivor_action_occurrences"], sort_keys=True)
    removals = json.dumps(
        summary["removed_action_occurrences_by_downstream_constraint"], sort_keys=True
    )
    text = f"""# Anchor constraint-intersection audit

## Boundary

{report['claim_boundary']}. This is not a counterfactual threshold ablation.

## Results

- Decisions: {summary['event_count']}
- Scan-empty decisions: {summary['scan_empty_count']}
- Scan-nonempty decisions: {summary['scan_nonempty_count']}
- Final temporary-empty decisions: {summary['final_temporary_empty_count']}
- First empty constraint: `{first_empty}`
- Scan survivor occurrences: `{survivors}`
- Downstream removals: `{removals}`
- Temporary actions actually selected: {summary['temporary_action_selected_count']}

The learned selector never received a temporary subgoal in these decisions. The
scan-safe residual is a 0.6 m, -30 degree candidate, and the active directional-yield
constraint removes it. Diagnose candidate/constraint compatibility and scenario
feasibility before changing a safety threshold or retraining the policy.
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
