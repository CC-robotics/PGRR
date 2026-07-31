#!/usr/bin/env python3
"""Summarize explicitly selected episode artifacts into a comparison CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def summarize(prefix: Path) -> dict[str, Any]:
    metadata = json.loads(prefix.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    outcome = json.loads(prefix.with_suffix(".outcome.json").read_text(encoding="utf-8"))
    stream_path = prefix.with_suffix(".jsonl")
    rows = [json.loads(line) for line in stream_path.read_text(encoding="utf-8").splitlines()]
    if not rows:
        raise ValueError(f"empty episode stream: {stream_path}")
    outcome_physical_distance = outcome.get("physical_goal_distance_m")
    if isinstance(outcome_physical_distance, (int, float)) and math.isfinite(
        outcome_physical_distance
    ):
        actual_goal_distance = float(outcome_physical_distance)
        actual_goal_distance_source = "outcome_terminal_snapshot"
    else:
        actual_goal_distance = math.dist(
            rows[-1]["goal"][:2], rows[-1]["privileged"]["robot_pose"][:2]
        )
        actual_goal_distance_source = "last_sample"
    return {
        "episode_id": metadata["episode_id"],
        "scenario_id": metadata["scenario_id"],
        "seed": metadata["seed"],
        "source_policy": metadata["source_policy"],
        "project_commit": metadata["project_commit"],
        "outcome": outcome["outcome"],
        "sample_count": len(rows),
        "sim_duration_s": float(rows[-1]["timestamp"]),
        "progress_m": float(rows[0]["distance_to_goal"] - rows[-1]["distance_to_goal"]),
        "actual_goal_distance_m": actual_goal_distance,
        "actual_goal_distance_source": actual_goal_distance_source,
        "max_localization_error_m": max(
            math.dist(row["robot_pose"][:2], row["privileged"]["robot_pose"][:2]) for row in rows
        ),
        "min_human_distance_m": min(
            float(row["privileged"]["nearest_human_distance"]) for row in rows
        ),
        "min_lidar_m": min(float(row["nearest_obstacle_distance"]) for row in rows),
        "recovery_actions": sum(int(row["recovery_action"]) != 24 for row in rows),
        "raw_sha256": hashlib.sha256(stream_path.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summaries = [summarize(prefix) for prefix in args.prefix]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summaries)


if __name__ == "__main__":
    main()
