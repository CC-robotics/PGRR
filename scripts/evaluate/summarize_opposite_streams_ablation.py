#!/usr/bin/env python3
"""Summarize retained opposite-stream train failures without dropping episodes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EPISODES = (
    ("Iteration 4", "3adfd3c", "r1", "sequence-unaware labels"),
    ("Turn memory", "c071950", "r1", "rejected 5 s turn commitment"),
    ("Iteration 5", "d4bf31b", "r2", "rejected immediate WAIT exhaustion"),
)


def _load(tag: str, repeat: str) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    stem = f"opposite_streams_high_train_s01620_{tag}_bc_dagger_{repeat}_dwb"
    raw = ROOT / "data/raw" / f"{stem}.jsonl"
    outcome = ROOT / "data/raw" / f"{stem}.outcome.json"
    if not raw.is_file() or not outcome.is_file():
        raise FileNotFoundError(f"missing retained episode: {stem}")
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
    return raw, rows, json.loads(outcome.read_text(encoding="utf-8"))


def _turn_switches(rows: list[dict[str, Any]]) -> int:
    runs: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        reason = str(row["recovery_reason"])
        if not reason.startswith("emergency_turn_"):
            continue
        if not runs or reason != runs[-1][1] or index > runs[-1][0] + 1:
            runs.append((index, reason))
        else:
            runs[-1] = index, reason
    return sum(first[1] != second[1] for first, second in pairwise(runs))


def main() -> None:
    output = ROOT / "outputs/pilot/opposite_streams_train_ablation.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for name, tag, repeat, description in EPISODES:
        raw, rows, outcome = _load(tag, repeat)
        reasons = Counter(str(row["recovery_reason"]) for row in rows)
        actions = Counter(int(row["recovery_action"]) for row in rows)
        final_physical_distance = math.dist(
            rows[-1]["goal"][:2], rows[-1]["privileged"]["robot_pose"][:2]
        )
        records.append(
            {
                "method": name,
                "project_commit": tag,
                "description": description,
                "outcome": outcome["outcome"],
                "samples": len(rows),
                "net_progress_m": float(rows[0]["distance_to_goal"])
                - float(rows[-1]["distance_to_goal"]),
                "final_physical_goal_distance_m": final_physical_distance,
                "minimum_human_distance_m": min(
                    float(row["privileged"]["nearest_human_distance"]) for row in rows
                ),
                "emergency_samples": sum(int(row["recovery_state"]) == 4 for row in rows),
                "policy_recovery_samples": sum(
                    int(row["recovery_state"]) != 4 and int(row["recovery_action"]) != 24
                    for row in rows
                ),
                "nominal_or_continue_samples": sum(
                    int(row["recovery_state"]) != 4 and int(row["recovery_action"]) == 24
                    for row in rows
                ),
                "wait_id_samples": actions[21],
                "backup_id_samples": actions[22],
                "temporary_subgoal_samples": sum(actions[action_id] for action_id in range(21)),
                "emergency_turn_samples": reasons["emergency_turn_left"]
                + reasons["emergency_turn_right"],
                "turn_side_switches": _turn_switches(rows),
                "last_60s_progress_m": float(rows[-600]["distance_to_goal"])
                - float(rows[-1]["distance_to_goal"]),
                "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            }
        )
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} retained ablation rows to {output}")


if __name__ == "__main__":
    main()
