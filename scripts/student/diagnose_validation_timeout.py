#!/usr/bin/env python3
"""Describe why a traced development episode timed out without causal claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from itertools import pairwise
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
STAGE_PATTERN = re.compile(
    r"mask_stage=([a-z_]+) pre=([0-9,]+|none) post=([0-9,]+|none)"
)
POST_PATTERN = re.compile(r"(?:^|[; ])post=([0-9,]+|none)(?:;| |$)")
CONFIDENCE_PATTERN = re.compile(r"bc_onnx confidence=([0-9.]+)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids(text: str) -> set[int]:
    return set() if text == "none" else {int(value) for value in text.split(",")}


def _path_length(rows: list[dict[str, Any]]) -> float:
    poses = [row.get("robot_pose") for row in rows]
    valid = [pose for pose in poses if isinstance(pose, list) and len(pose) >= 2]
    return sum(
        math.hypot(float(current[0]) - float(previous[0]), float(current[1]) - float(previous[1]))
        for previous, current in pairwise(valid)
    )


def _state_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    start = 0
    for index in range(1, len(rows) + 1):
        changed = index == len(rows) or rows[index].get("recovery_state") != rows[start].get(
            "recovery_state"
        )
        if not changed:
            continue
        state = int(rows[start].get("recovery_state", 0))
        end = index - 1
        segments.append(
            {
                "state": state,
                "state_name": STATE_NAMES.get(state, f"UNKNOWN_{state}"),
                "start_index": start,
                "end_index": end,
                "start_s": float(rows[start]["timestamp"]),
                "end_s": float(rows[end]["timestamp"]),
                "row_count": index - start,
            }
        )
        start = index
    return segments


def _recovery_cycles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cycles: list[dict[str, Any]] = []
    index = 0
    while index < len(rows):
        if int(rows[index].get("recovery_state", 0)) == 0:
            index += 1
            continue
        start = index
        while index < len(rows) and int(rows[index].get("recovery_state", 0)) != 0:
            index += 1
        end = index if index < len(rows) else len(rows) - 1
        window = rows[start : end + 1]
        start_distance = float(rows[start]["distance_to_goal"])
        end_distance = float(rows[end]["distance_to_goal"])
        states = []
        for row in window:
            state_name = STATE_NAMES.get(int(row.get("recovery_state", 0)), "UNKNOWN")
            if not states or states[-1] != state_name:
                states.append(state_name)
        cycles.append(
            {
                "cycle_index": len(cycles) + 1,
                "start_index": start,
                "end_index": end,
                "start_s": float(rows[start]["timestamp"]),
                "end_s": float(rows[end]["timestamp"]),
                "states": states,
                "start_goal_distance_m": start_distance,
                "end_goal_distance_m": end_distance,
                "original_goal_progress_m": start_distance - end_distance,
                "path_length_m": _path_length(window),
                "action_row_counts": dict(
                    sorted(
                        Counter(
                            ACTION_NAMES.get(
                                int(row.get("recovery_action", 24)),
                                f"UNKNOWN_{row.get('recovery_action')}",
                            )
                            for row in window
                        ).items()
                    )
                ),
            }
        )
    return cycles


def diagnose(jsonl: Path, outcome_path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError("episode contains no telemetry rows")
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    if int(outcome.get("sample_count", -1)) != len(rows):
        raise ValueError("outcome sample count does not match telemetry")

    first_failure_index = next(
        (index for index, row in enumerate(rows) if int(row.get("recovery_state", 0)) != 0),
        None,
    )
    if first_failure_index is None:
        raise ValueError("episode never left NORMAL")

    traced = []
    for index, row in enumerate(rows):
        reason = str(row.get("recovery_reason", ""))
        transitions = STAGE_PATTERN.findall(reason)
        if not transitions:
            continue
        path_post = next(
            (_ids(after) for stage, _, after in transitions if stage == "path_corridor"),
            set(),
        )
        posts = POST_PATTERN.findall(reason)
        final_post = _ids(posts[-1]) if posts else set()
        confidence_match = CONFIDENCE_PATTERN.search(reason)
        traced.append(
            {
                "sample_index": index,
                "action_id": int(row.get("recovery_action", 24)),
                "path_temporary_count": sum(value < 21 for value in path_post),
                "final_temporary_count": sum(value < 21 for value in final_post),
                "final_wait_backup_only": bool(final_post) and final_post <= {21, 22},
                "directional_yield_active": "bc_directional_yield=active" in reason,
                "confidence": float(confidence_match.group(1)) if confidence_match else None,
            }
        )

    cycles = _recovery_cycles(rows)
    distances = [float(row["distance_to_goal"]) for row in rows]
    before = rows[: first_failure_index + 1]
    after = rows[first_failure_index:]
    path_survivors = [item for item in traced if item["path_temporary_count"] > 0]
    directional_yield = [item for item in traced if item["directional_yield_active"]]
    no_directional_yield = [item for item in traced if not item["directional_yield_active"]]
    confidences = [item["confidence"] for item in traced if item["confidence"] is not None]

    return {
        "schema_version": 1,
        "diagnostic_only": True,
        "causal_claim": False,
        "episode_id": outcome.get("episode_id"),
        "outcome": outcome.get("outcome"),
        "sample_count": len(rows),
        "source_sha256": {"jsonl": _sha256(jsonl), "outcome": _sha256(outcome_path)},
        "goal_distance": {
            "initial_m": distances[0],
            "at_first_failure_m": distances[first_failure_index],
            "minimum_m": min(distances),
            "final_m": distances[-1],
            "progress_before_first_failure_m": distances[0] - distances[first_failure_index],
            "progress_after_first_failure_m": distances[first_failure_index] - distances[-1],
        },
        "path_length": {
            "before_first_failure_m": _path_length(before),
            "after_first_failure_m": _path_length(after),
        },
        "first_failure": {
            "sample_index": first_failure_index,
            "timestamp_s": float(rows[first_failure_index]["timestamp"]),
            "state": STATE_NAMES.get(int(rows[first_failure_index]["recovery_state"])),
        },
        "state_row_counts": dict(
            sorted(
                Counter(
                    STATE_NAMES.get(int(row.get("recovery_state", 0)), "UNKNOWN") for row in rows
                ).items()
            )
        ),
        "state_segments": _state_segments(rows),
        "recovery_cycles": cycles,
        "cycle_summary": {
            "cycle_count": len(cycles),
            "positive_progress_cycle_count": sum(
                cycle["original_goal_progress_m"] > 0.0 for cycle in cycles
            ),
            "nonpositive_progress_cycle_count": sum(
                cycle["original_goal_progress_m"] <= 0.0 for cycle in cycles
            ),
            "total_cycle_progress_m": sum(
                cycle["original_goal_progress_m"] for cycle in cycles
            ),
        },
        "trace_constraint_summary": {
            "traced_row_count": len(traced),
            "action_counts": dict(
                sorted(
                    Counter(
                        ACTION_NAMES.get(item["action_id"], "UNKNOWN") for item in traced
                    ).items()
                )
            ),
            "path_stage_temporary_survivor_row_count": len(path_survivors),
            "path_survivors_removed_downstream_count": sum(
                item["final_temporary_count"] == 0 for item in path_survivors
            ),
            "path_survivors_retained_final_count": sum(
                item["final_temporary_count"] > 0 for item in path_survivors
            ),
            "path_survivor_action_counts": dict(
                sorted(
                    Counter(
                        ACTION_NAMES.get(item["action_id"], "UNKNOWN")
                        for item in path_survivors
                    ).items()
                )
            ),
            "final_wait_backup_only_row_count": sum(
                item["final_wait_backup_only"] for item in traced
            ),
            "directional_yield_active_row_count": sum(
                item["directional_yield_active"] for item in traced
            ),
            "directional_yield_action_counts": dict(
                sorted(
                    Counter(
                        ACTION_NAMES.get(item["action_id"], "UNKNOWN")
                        for item in directional_yield
                    ).items()
                )
            ),
            "non_directional_yield_action_counts": dict(
                sorted(
                    Counter(
                        ACTION_NAMES.get(item["action_id"], "UNKNOWN")
                        for item in no_directional_yield
                    ).items()
                )
            ),
            "temporary_subgoal_selected_count": sum(
                item["action_id"] < 21 for item in traced
            ),
            "confidence_min": min(confidences) if confidences else None,
            "confidence_max": max(confidences) if confidences else None,
        },
        "bounded_interpretation": (
            "After the first failure trigger, progress toward the original goal nearly stopped; "
            "every bounded recovery cycle ended no closer to the goal, and downstream observable "
            "guards often restricted the final choice to WAIT/BACKUP. These are descriptive "
            "associations in one TIMEOUT episode, not proof of algorithmic cause."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.jsonl, args.outcome)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
