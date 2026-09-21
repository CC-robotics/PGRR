#!/usr/bin/env python3
"""Summarize recovery decisions and state transitions in an episode JSONL."""

from __future__ import annotations

import argparse
import json
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
STATE_NAMES = {
    0: "NORMAL",
    1: "PENDING_RECOVERY",
    2: "RECOVERY",
    3: "REJOIN",
    4: "EMERGENCY_STOP",
    5: "FAILED",
    6: "SUCCEEDED",
}


def _reason_category(reason: str) -> str:
    if "bc_onnx confidence=" in reason:
        return "bc_onnx_decision"
    return reason or "empty"


def _compress(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: object = object()
    for index, row in enumerate(rows):
        value = row.get(field)
        if value != previous:
            item = {
                "sample_index": index,
                "timestamp_s": round(float(row["timestamp"]), 6),
                field: value,
            }
            if field == "recovery_state" and value is not None:
                item["state_name"] = STATE_NAMES.get(int(value), f"UNKNOWN_{value}")
            output.append(item)
            previous = value
    return output


def summarize_recovery(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError(f"episode contains no rows: {path}")

    decision_events: list[dict[str, Any]] = []
    previous_signature: tuple[int, str] | None = None
    for index, row in enumerate(rows):
        action_id = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", ""))
        signature = (action_id, reason)
        if signature == previous_signature:
            continue
        decision_events.append(
            {
                "sample_index": index,
                "timestamp_s": round(float(row["timestamp"]), 6),
                "action_id": action_id,
                "action_name": ACTION_NAMES.get(action_id, f"UNKNOWN_{action_id}"),
                "reason_category": _reason_category(reason),
            }
        )
        previous_signature = signature

    action_counts = Counter(event["action_name"] for event in decision_events)
    reason_counts = Counter(event["reason_category"] for event in decision_events)
    original_goals = {tuple(row.get("goal") or []) for row in rows}
    return {
        "source": str(path),
        "sample_count": len(rows),
        "state_transitions": _compress(rows, "recovery_state"),
        "decision_event_count": len(decision_events),
        "decision_action_counts": dict(sorted(action_counts.items())),
        "decision_reason_counts": dict(sorted(reason_counts.items())),
        "temporary_subgoal_decision_count": sum(
            event["action_id"] < 21 for event in decision_events
        ),
        "original_goal_restored_event_count": reason_counts["original_goal_restored"],
        "distinct_logged_task_goals": len(original_goals),
        "decision_timeline": decision_events,
        "diagnostic_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_jsonl", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize_recovery(args.episode_jsonl), indent=2))


if __name__ == "__main__":
    main()
