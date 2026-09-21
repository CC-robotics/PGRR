#!/usr/bin/env python3
"""Attribute recovery decisions to masks, learned policy, and emergency guards."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
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
POST_MASK_PATTERN = re.compile(r"(?:^|[; ])post=([0-9,]+|none)(?:;| |$)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _origin(reason: str) -> str:
    if "bc_onnx confidence=" in reason:
        return "LEARNED_POLICY"
    if reason.startswith("emergency_"):
        return "EMERGENCY_GUARD"
    if reason.startswith("safety_clear_"):
        return "SAFETY_CLEAR"
    if reason in {"original_goal_restored", "recovery_action_complete"}:
        return "RECOVERY_LIFECYCLE"
    return "OTHER"


def parse_final_post_mask(reason: str) -> tuple[int, ...] | None:
    """Return the last logged post-constraint action set, if present."""

    matches = POST_MASK_PATTERN.findall(reason)
    if not matches:
        return None
    value = matches[-1]
    if value == "none":
        return ()
    return tuple(int(item) for item in value.split(","))


def _decision_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    previous: tuple[int, str] | None = None
    for index, row in enumerate(rows):
        action_id = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", ""))
        signature = (action_id, reason)
        if signature == previous:
            continue
        allowed = parse_final_post_mask(reason) if "bc_onnx confidence=" in reason else None
        events.append(
            {
                "sample_index": index,
                "timestamp_s": float(row["timestamp"]),
                "action_id": action_id,
                "action_name": ACTION_NAMES.get(action_id, f"UNKNOWN_{action_id}"),
                "origin": _origin(reason),
                "reason": reason,
                "allowed_action_ids": allowed,
            }
        )
        previous = signature
    return events


def analyze_episode(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = _decision_events(rows)
    learned_rows = []
    for event_index, event in enumerate(events):
        if event["origin"] != "LEARNED_POLICY":
            continue
        allowed = event["allowed_action_ids"]
        parseable = allowed is not None
        only_wait_backup = parseable and bool(allowed) and set(allowed) <= WAIT_BACKUP_IDS
        alternative_available = parseable and any(
            action_id not in WAIT_BACKUP_IDS for action_id in allowed
        )
        next_event = events[event_index + 1] if event_index + 1 < len(events) else None
        learned_rows.append(
            {
                **event,
                "mask_parseable": parseable,
                "allowed_action_ids_text": (
                    ",".join(str(action_id) for action_id in allowed)
                    if allowed is not None
                    else "unknown"
                ),
                "only_wait_backup_allowed": only_wait_backup,
                "alternative_action_available": alternative_available,
                "selected_wait_or_backup": event["action_id"] in WAIT_BACKUP_IDS,
                "selected_action_in_logged_mask": (
                    event["action_id"] in allowed if allowed is not None else None
                ),
                "next_event_origin": next_event["origin"] if next_event else None,
                "next_event_action": next_event["action_name"] if next_event else None,
                "next_event_delay_s": (
                    round(next_event["timestamp_s"] - event["timestamp_s"], 6)
                    if next_event
                    else None
                ),
                "immediately_followed_by_emergency_guard": (
                    next_event is not None and next_event["origin"] == "EMERGENCY_GUARD"
                ),
            }
        )
    return learned_rows


def analyze_pilot(progress_path: Path, data_root: Path) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    learned_events = []
    all_origin_counts: Counter[str] = Counter()
    emergency_action_counts: Counter[str] = Counter()
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        if _sha256(path) != run["artifact_sha256"]["raw_jsonl"]:
            raise ValueError(f"raw log hash mismatch: {path}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        events = _decision_events(rows)
        all_origin_counts.update(event["origin"] for event in events)
        emergency_action_counts.update(
            event["action_name"]
            for event in events
            if event["origin"] == "EMERGENCY_GUARD"
        )
        episode_learned = analyze_episode(rows)
        for event in episode_learned:
            event.update(
                {
                    "family_index": pair["family_index"],
                    "family": pair["family"],
                    "episode_id": episode_id,
                }
            )
        learned_events.extend(episode_learned)

    parseable = [event for event in learned_events if event["mask_parseable"]]
    alternatives = [event for event in parseable if event["alternative_action_available"]]
    aggregate = {
        "raw_hashes_verified": True,
        "learned_decision_event_count": len(learned_events),
        "decision_origin_counts": dict(sorted(all_origin_counts.items())),
        "emergency_action_counts": dict(sorted(emergency_action_counts.items())),
        "parseable_final_mask_count": len(parseable),
        "unknown_final_mask_count": len(learned_events) - len(parseable),
        "only_wait_backup_allowed_count": sum(
            event["only_wait_backup_allowed"] for event in parseable
        ),
        "alternative_action_available_count": len(alternatives),
        "wait_backup_selected_with_alternative_count": sum(
            event["selected_wait_or_backup"] for event in alternatives
        ),
        "selected_action_outside_logged_mask_count": sum(
            event["selected_action_in_logged_mask"] is False for event in parseable
        ),
        "immediately_followed_by_emergency_guard_count": sum(
            event["immediately_followed_by_emergency_guard"] for event in learned_events
        ),
        "learned_action_counts": dict(
            sorted(Counter(event["action_name"] for event in learned_events).items())
        ),
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "train_only_descriptive_attribution_no_causal_claim",
        "aggregate": aggregate,
        "learned_events": learned_events,
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = report["learned_events"]
    if not rows:
        raise ValueError("no learned-policy decision events found")
    fields = [
        "family_index",
        "family",
        "episode_id",
        "sample_index",
        "timestamp_s",
        "action_id",
        "action_name",
        "allowed_action_ids_text",
        "mask_parseable",
        "only_wait_backup_allowed",
        "alternative_action_available",
        "selected_wait_or_backup",
        "selected_action_in_logged_mask",
        "next_event_origin",
        "next_event_action",
        "next_event_delay_s",
        "immediately_followed_by_emergency_guard",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
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
