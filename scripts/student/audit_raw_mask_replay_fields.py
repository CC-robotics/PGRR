#!/usr/bin/env python3
"""Audit whether existing PGRR JSONL logs can replay upstream mask layers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_vector(value: Any, length: int) -> bool:
    return isinstance(value, list) and len(value) == length


def _valid_path(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(point, list) and len(point) == 2 for point in value)
    )


def _learned_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    previous: tuple[int, str] | None = None
    for row in rows:
        action = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", ""))
        signature = action, reason
        if signature == previous:
            continue
        previous = signature
        if "bc_onnx confidence=" in reason:
            selected.append(row)
    return selected


def assess_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    learned = _learned_rows(rows)
    field_names = (
        "robot_pose_len3",
        "resampled_lidar_len180",
        "global_path_nonempty_xy",
        "original_scan_ranges",
        "scan_angle_min",
        "scan_angle_increment",
        "occupancy_grid",
        "map_resolution",
        "map_origin",
        "task_corridor_path",
        "runtime_mask_parameters",
    )
    presence = Counter({name: 0 for name in field_names})
    for row in learned:
        presence.update(
            {
                "robot_pose_len3": _valid_vector(row.get("robot_pose"), 3),
                "resampled_lidar_len180": _valid_vector(row.get("lidar"), 180),
                "global_path_nonempty_xy": _valid_path(row.get("global_path")),
                "original_scan_ranges": isinstance(row.get("scan_ranges"), list),
                "scan_angle_min": row.get("scan_angle_min") is not None,
                "scan_angle_increment": row.get("scan_angle_increment") is not None,
                "occupancy_grid": row.get("occupancy_grid") is not None,
                "map_resolution": row.get("map_resolution") is not None,
                "map_origin": row.get("map_origin") is not None,
                "task_corridor_path": _valid_path(row.get("task_corridor_path")),
                "runtime_mask_parameters": isinstance(row.get("runtime_mask_parameters"), dict),
            }
        )
    count = len(learned)
    complete = {name: int(presence[name]) for name in field_names}
    example_shapes = {}
    if learned:
        for name, value in sorted(learned[0].items()):
            if isinstance(value, list):
                example_shapes[name] = {
                    "length": len(value),
                    "nested_first_length": (
                        len(value[0]) if value and isinstance(value[0], list) else None
                    ),
                }
    return {
        "learned_decision_count": count,
        "field_complete_counts": complete,
        "observed_top_level_fields": sorted(learned[0]) if learned else [],
        "example_list_shapes": example_shapes,
        "map_layer_exact_replay": bool(
            count
            and complete["robot_pose_len3"] == count
            and complete["occupancy_grid"] == count
            and complete["map_resolution"] == count
            and complete["map_origin"] == count
            and complete["runtime_mask_parameters"] == count
        ),
        "scan_layer_exact_replay": bool(
            count
            and complete["original_scan_ranges"] == count
            and complete["scan_angle_min"] == count
            and complete["scan_angle_increment"] == count
            and complete["runtime_mask_parameters"] == count
        ),
        "scan_layer_approximate_replay": bool(
            count and complete["resampled_lidar_len180"] == count
        ),
        "corridor_layer_exact_replay": bool(
            count
            and complete["robot_pose_len3"] == count
            and complete["task_corridor_path"] == count
            and complete["runtime_mask_parameters"] == count
        ),
        "corridor_layer_approximate_replay": bool(
            count
            and complete["robot_pose_len3"] == count
            and complete["global_path_nonempty_xy"] == count
        ),
    }


def audit_pilot(progress_path: Path, data_root: Path) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    episodes = []
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        if _sha256(path) != run["artifact_sha256"]["raw_jsonl"]:
            raise ValueError(f"raw log hash mismatch: {path}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        assessment = assess_rows(rows)
        assessment.update(
            {
                "family_index": pair["family_index"],
                "family": pair["family"],
                "episode_id": episode_id,
            }
        )
        episodes.append(assessment)

    total = sum(item["learned_decision_count"] for item in episodes)
    fields = sorted(episodes[0]["field_complete_counts"])
    aggregate_counts = {
        field: sum(item["field_complete_counts"][field] for item in episodes)
        for field in fields
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "field_availability_not_exact_replay",
        "raw_hashes_verified": True,
        "learned_decision_count": total,
        "field_complete_counts": aggregate_counts,
        "exact_replay_supported": {
            "map_connectivity": bool(
                total
                and aggregate_counts["robot_pose_len3"] == total
                and aggregate_counts["occupancy_grid"] == total
                and aggregate_counts["map_resolution"] == total
                and aggregate_counts["map_origin"] == total
                and aggregate_counts["runtime_mask_parameters"] == total
            ),
            "observable_scan": bool(
                total
                and aggregate_counts["original_scan_ranges"] == total
                and aggregate_counts["scan_angle_min"] == total
                and aggregate_counts["scan_angle_increment"] == total
                and aggregate_counts["runtime_mask_parameters"] == total
            ),
            "path_corridor": bool(
                total
                and aggregate_counts["robot_pose_len3"] == total
                and aggregate_counts["task_corridor_path"] == total
                and aggregate_counts["runtime_mask_parameters"] == total
            ),
        },
        "approximate_replay_supported": {
            "observable_scan": bool(
                total and aggregate_counts["resampled_lidar_len180"] == total
            ),
            "path_corridor": bool(
                total
                and aggregate_counts["robot_pose_len3"] == total
                and aggregate_counts["global_path_nonempty_xy"] == total
            ),
        },
        "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_pilot(args.progress, args.data_root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "learned_decision_count": report["learned_decision_count"],
                "field_complete_counts": report["field_complete_counts"],
                "exact_replay_supported": report["exact_replay_supported"],
                "approximate_replay_supported": report["approximate_replay_supported"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
