#!/usr/bin/env python3
"""Reconstruct logged pre/post action-mask constraints for PGRR decisions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ACTION_NAMES = {
    **{index: f"SUBGOAL_{index}" for index in range(21)},
    21: "WAIT",
    22: "BACKUP",
    23: "REPLAN",
    24: "CONTINUE",
}
WAIT_BACKUP_IDS = {21, 22}

MASK_STEP_PATTERN = re.compile(
    r"\bpre=([0-9,]+|none)\s+(post|final)=([0-9,]+|none)(?:\s|;|$)"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_ids(value: str) -> tuple[int, ...]:
    return () if value == "none" else tuple(int(item) for item in value.split(","))


def parse_mask_steps(reason: str) -> list[dict[str, Any]]:
    """Parse ordered named mask transitions from one telemetry reason."""

    recorded_steps = []
    for segment in reason.split(";"):
        match = MASK_STEP_PATTERN.search(segment)
        if not match:
            continue
        stripped = segment.strip()
        first_token = stripped.split(maxsplit=1)[0]
        constraint = first_token.split("=", maxsplit=1)[0]
        before = _parse_ids(match.group(1))
        after = _parse_ids(match.group(3))
        recorded_steps.append(
            {
                "constraint": constraint,
                "endpoint_field": match.group(2),
                "pre": before,
                "post": after,
                "removed": tuple(sorted(set(before) - set(after))),
                "added": tuple(sorted(set(after) - set(before))),
            }
        )
    steps = []
    for step in recorded_steps:
        if steps and steps[-1]["post"] != step["pre"]:
            before = steps[-1]["post"]
            after = step["pre"]
            steps.append(
                {
                    "constraint": (
                        f"UNLOGGED_AFTER_{steps[-1]['constraint']}_BEFORE_"
                        f"{step['constraint']}"
                    ),
                    "endpoint_field": "inferred_gap",
                    "pre": before,
                    "post": after,
                    "removed": tuple(sorted(set(before) - set(after))),
                    "added": tuple(sorted(set(after) - set(before))),
                }
            )
        steps.append(step)
    return steps


def collapse_source(steps: list[dict[str, Any]]) -> str:
    """Name the first logged step that removes every non-WAIT/BACKUP option."""

    if not steps:
        return "NO_PARSEABLE_MASK_STEP"
    for step in steps:
        before_has_alternative = any(action not in WAIT_BACKUP_IDS for action in step["pre"])
        after_only_wait_backup = bool(step["post"]) and set(step["post"]) <= WAIT_BACKUP_IDS
        if before_has_alternative and after_only_wait_backup:
            return str(step["constraint"])
    final = steps[-1]["post"]
    if final and set(final) <= WAIT_BACKUP_IDS:
        return "UPSTREAM_BEFORE_FIRST_LOGGED_STEP"
    return "NOT_COLLAPSED_TO_WAIT_BACKUP"


def _decision_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    previous: tuple[int, str] | None = None
    for index, row in enumerate(rows):
        action_id = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", ""))
        signature = (action_id, reason)
        if signature == previous:
            continue
        previous = signature
        if "bc_onnx confidence=" not in reason:
            continue
        steps = parse_mask_steps(reason)
        events.append(
            {
                "sample_index": index,
                "timestamp_s": float(row["timestamp"]),
                "action_id": action_id,
                "action_name": ACTION_NAMES.get(action_id, f"UNKNOWN_{action_id}"),
                "steps": steps,
                "collapse_source": collapse_source(steps),
            }
        )
    return events


def analyze_pilot(progress_path: Path, data_root: Path) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    events = []
    step_occurrences: Counter[str] = Counter()
    removed_by_constraint: defaultdict[str, Counter[str]] = defaultdict(Counter)
    added_by_constraint: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        if _sha256(path) != run["artifact_sha256"]["raw_jsonl"]:
            raise ValueError(f"raw log hash mismatch: {path}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        episode_events = _decision_events(rows)
        for event in episode_events:
            event.update(
                {
                    "family_index": pair["family_index"],
                    "family": pair["family"],
                    "episode_id": episode_id,
                }
            )
            for step in event["steps"]:
                name = step["constraint"]
                step_occurrences[name] += 1
                removed_by_constraint[name].update(
                    ACTION_NAMES.get(action, f"UNKNOWN_{action}") for action in step["removed"]
                )
                added_by_constraint[name].update(
                    ACTION_NAMES.get(action, f"UNKNOWN_{action}") for action in step["added"]
                )
        events.extend(episode_events)

    aggregate = {
        "raw_hashes_verified": True,
        "learned_decision_event_count": len(events),
        "events_with_mask_steps": sum(bool(event["steps"]) for event in events),
        "collapse_source_counts": dict(
            sorted(Counter(event["collapse_source"] for event in events).items())
        ),
        "constraint_step_occurrences": dict(sorted(step_occurrences.items())),
        "removed_action_counts_by_constraint": {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(removed_by_constraint.items())
        },
        "added_action_counts_by_constraint": {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(added_by_constraint.items())
        },
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "logged_mask_reconstruction_not_counterfactual_ablation",
        "aggregate": aggregate,
        "events": events,
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = []
    for event in report["events"]:
        if not event["steps"]:
            rows.append(
                {
                    "family": event["family"],
                    "episode_id": event["episode_id"],
                    "sample_index": event["sample_index"],
                    "timestamp_s": event["timestamp_s"],
                    "selected_action": event["action_name"],
                    "step_index": "",
                    "constraint": "",
                    "pre": "unknown",
                    "post": "unknown",
                    "removed": "",
                    "added": "",
                    "collapse_source": event["collapse_source"],
                }
            )
        for step_index, step in enumerate(event["steps"], start=1):
            rows.append(
                {
                    "family": event["family"],
                    "episode_id": event["episode_id"],
                    "sample_index": event["sample_index"],
                    "timestamp_s": event["timestamp_s"],
                    "selected_action": event["action_name"],
                    "step_index": step_index,
                    "constraint": step["constraint"],
                    "pre": ",".join(map(str, step["pre"])),
                    "post": ",".join(map(str, step["post"])),
                    "removed": ",".join(
                        ACTION_NAMES.get(action, f"UNKNOWN_{action}")
                        for action in step["removed"]
                    ),
                    "added": ",".join(
                        ACTION_NAMES.get(action, f"UNKNOWN_{action}")
                        for action in step["added"]
                    ),
                    "collapse_source": event["collapse_source"],
                }
            )
    if not rows:
        raise ValueError("no learned-policy events found")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_pilot(args.progress, args.data_root)
    write_outputs(report, args.json_output, args.csv_output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
