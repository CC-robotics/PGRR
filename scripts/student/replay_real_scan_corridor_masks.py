#!/usr/bin/env python3
"""Approximately replay scan and path-corridor masks at logged BC decisions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.action_mask import apply_observable_scan_mask, apply_path_corridor_mask
from ramp_core.recovery.safety import collision_latched_motion_clearance
from ramp_core.types import Pose2D

ACTION_COUNT = 25
SUBGOAL_IDS = set(range(21))
YIELD_PRE = re.compile(r"bc_yield_mask=active\s+pre=([0-9,]+|none)\s+post=")
RECOVERY_COUNT = re.compile(r"bc_recurrent_escape=.*?\bcount=(\d+)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids(value: str) -> set[int]:
    return set() if value == "none" else {int(item) for item in value.split(",")}


def _learned_rows(rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    selected = []
    previous: tuple[int, str] | None = None
    for index, row in enumerate(rows):
        action = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", ""))
        signature = action, reason
        if signature == previous:
            continue
        previous = signature
        if "bc_onnx confidence=" in reason:
            selected.append((index, row))
    return selected


def replay_row(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = str(row.get("recovery_reason", ""))
    match = YIELD_PRE.search(reason)
    if not match:
        return None
    logged = _ids(match.group(1)) & SUBGOAL_IDS
    pose_values = row["robot_pose"]
    pose = Pose2D(float(pose_values[0]), float(pose_values[1]), float(pose_values[2]))
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    collision_risk = float(row["failure_prediction"][0])
    action_clearance = 0.25
    swept_clearance = 0.48
    if collision_risk >= 0.65:
        action_clearance = collision_latched_motion_clearance(
            configured_action_clearance_m=0.90,
            stop_clearance_m=0.85,
            release_hysteresis_m=0.05,
        )
        swept_clearance = max(swept_clearance, action_clearance)
    scan_mask = apply_observable_scan_mask(
        mask,
        np.asarray(row["lidar"], dtype=np.float64),
        angle_min=math.radians(-135.0),
        angle_increment=math.radians(270.0) / 179.0,
        swept_clearance_m=swept_clearance,
        target_clearance_m=action_clearance,
        backup_distance_m=0.45,
        allow_unobserved_backup=False,
        allow_initial_overlap_when_separating=collision_risk >= 0.65,
    )
    count_match = RECOVERY_COUNT.search(reason)
    recovery_count = int(count_match.group(1)) if count_match else None
    corridor_width = 2.5 if recovery_count is not None and recovery_count >= 2 else 0.65
    corridor_mask = apply_path_corridor_mask(
        scan_mask,
        pose,
        tuple((float(point[0]), float(point[1])) for point in row["global_path"]),
        maximum_deviation_m=corridor_width,
        backup_distance_m=0.45,
    )
    scan = set(np.flatnonzero(scan_mask[:21]).tolist())
    replayed = set(np.flatnonzero(corridor_mask[:21]).tolist())
    return {
        "logged_subgoal_ids": sorted(logged),
        "logged_subgoal_count": len(logged),
        "scan_subgoal_ids": sorted(scan),
        "scan_subgoal_count": len(scan),
        "replayed_subgoal_ids": sorted(replayed),
        "replayed_subgoal_count": len(replayed),
        "logged_not_in_replay": sorted(logged - replayed),
        "replay_not_in_logged": sorted(replayed - logged),
        "exact_subgoal_match": logged == replayed,
        "logged_is_subset_of_replay": logged <= replayed,
        "logged_empty_explained": not logged and not replayed,
        "corridor_width_m_assumed": corridor_width,
        "recovery_count_from_reason": recovery_count,
        "collision_risk": collision_risk,
    }


def analyze_pilot(progress_path: Path, data_root: Path) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    events = []
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        if _sha256(path) != run["artifact_sha256"]["raw_jsonl"]:
            raise ValueError(f"raw log hash mismatch: {path}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        for sample_index, row in _learned_rows(rows):
            replay = replay_row(row)
            if replay is None:
                continue
            replay.update(
                {
                    "family_index": pair["family_index"],
                    "family": pair["family"],
                    "episode_id": episode_id,
                    "sample_index": sample_index,
                    "timestamp_s": float(row["timestamp"]),
                }
            )
            events.append(replay)

    family_counts: dict[str, Counter[str]] = {}
    for event in events:
        counter = family_counts.setdefault(event["family"], Counter())
        counter["events"] += 1
        counter["logged_empty"] += int(event["logged_subgoal_count"] == 0)
        counter["logged_empty_explained"] += int(event["logged_empty_explained"])
        counter["exact_match"] += int(event["exact_subgoal_match"])
    aggregate = {
        "raw_hashes_verified": True,
        "yield_event_count": len(events),
        "logged_empty_count": sum(event["logged_subgoal_count"] == 0 for event in events),
        "logged_empty_explained_count": sum(event["logged_empty_explained"] for event in events),
        "logged_empty_scan_already_empty_count": sum(
            event["logged_subgoal_count"] == 0 and event["scan_subgoal_count"] == 0
            for event in events
        ),
        "logged_empty_corridor_finished_empty_count": sum(
            event["logged_subgoal_count"] == 0
            and event["scan_subgoal_count"] > 0
            and event["replayed_subgoal_count"] == 0
            for event in events
        ),
        "logged_empty_unexplained_count": sum(
            event["logged_subgoal_count"] == 0 and event["replayed_subgoal_count"] > 0
            for event in events
        ),
        "exact_subgoal_match_count": sum(event["exact_subgoal_match"] for event in events),
        "logged_subset_of_replay_count": sum(
            event["logged_is_subset_of_replay"] for event in events
        ),
        "events_with_replay_false_elimination": sum(
            bool(event["logged_not_in_replay"]) for event in events
        ),
        "family_counts": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(family_counts.items())
        },
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "approximate_resampled_scan_and_logged_path_replay",
        "assumptions": {
            "lidar_field_of_view_degrees": 270.0,
            "lidar_bins": 180,
            "normal_corridor_width_m": 0.65,
            "recurrent_corridor_width_m": 2.5,
            "recurrent_threshold": 2,
            "map_layer": "unknown_and_omitted",
            "synchronization": "episode_logger_samples_not_runtime_internal_snapshots",
        },
        "aggregate": aggregate,
        "events": events,
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = [
        "family",
        "episode_id",
        "sample_index",
        "timestamp_s",
        "collision_risk",
        "corridor_width_m_assumed",
        "logged_subgoal_count",
        "scan_subgoal_count",
        "replayed_subgoal_count",
        "logged_subgoal_ids",
        "scan_subgoal_ids",
        "replayed_subgoal_ids",
        "logged_not_in_replay",
        "replay_not_in_logged",
        "exact_subgoal_match",
        "logged_is_subset_of_replay",
        "logged_empty_explained",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for event in report["events"]:
            row = {name: event[name] for name in fields}
            for name in (
                "logged_subgoal_ids",
                "scan_subgoal_ids",
                "replayed_subgoal_ids",
                "logged_not_in_replay",
                "replay_not_in_logged",
            ):
                row[name] = ",".join(map(str, row[name]))
            writer.writerow(row)


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
