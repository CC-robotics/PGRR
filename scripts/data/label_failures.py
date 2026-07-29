#!/usr/bin/env python3
"""Generate dense rule and privileged-future failure labels for recorded episodes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml
from ramp_core.failure.labels import FailureType, generate_failure_labels
from ramp_core.failure.rules import RuleFailureConfig, TimedNavigationSample
from ramp_core.types import PlannerStatus

ROOT = Path(__file__).resolve().parents[2]


def _planner_status(value: Any) -> PlannerStatus:
    try:
        return PlannerStatus(int(value))
    except (TypeError, ValueError):
        return PlannerStatus.UNKNOWN


def _sample(row: dict[str, Any]) -> TimedNavigationSample:
    return TimedNavigationSample(
        timestamp=float(row["timestamp"]),
        position=(float(row["robot_pose"][0]), float(row["robot_pose"][1])),
        goal_distance=float(row["distance_to_goal"]),
        linear_velocity=float(row["robot_velocity"][0]),
        angular_velocity=float(row["robot_velocity"][1]),
        base_linear_command=float(row["base_cmd_vel"][0]),
        base_angular_command=float(row["base_cmd_vel"][1]),
        nearest_lidar_distance=float(row["nearest_obstacle_distance"]),
        planner_status=_planner_status(row["planner_status"]),
        goal_reached=float(row["distance_to_goal"]) <= 0.25,
    )


def _config(path: Path) -> tuple[RuleFailureConfig, dict[str, float]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    window_keys = {
        "offline_collision_lookahead_s",
        "positive_pre_failure_window_s",
        "positive_post_failure_window_s",
    }
    rule_values = {key: value for key, value in raw.items() if key not in window_keys}
    return RuleFailureConfig(**rule_values), {key: float(raw[key]) for key in window_keys}


def label_dataset(
    results_path: Path,
    config_path: Path,
    destination: Path,
    summary_path: Path,
) -> dict[str, Any]:
    records = list(csv.DictReader(results_path.open(encoding="utf-8")))
    rule_config, windows = _config(config_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_class_counts = np.zeros(len(FailureType), dtype=np.int64)
    onset_counts: Counter[str] = Counter()
    hard_negative_count = 0
    total_samples = 0
    with h5py.File(destination, "w") as target:
        target.attrs["schema_version"] = 1
        target.attrs["source_results"] = str(results_path.relative_to(ROOT))
        target.attrs["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
        episodes = target.create_group("episodes")
        for record in records:
            episode_id = record["episode_id"]
            stream_path = ROOT / "data" / "raw" / f"{episode_id}.jsonl"
            rows = [
                json.loads(line) for line in stream_path.read_text(encoding="utf-8").splitlines()
            ]
            samples = [_sample(row) for row in rows]
            collision_times = [
                float(row["timestamp"]) for row in rows if bool(row.get("collision", False))
            ]
            if record["outcome"] == "COLLISION" and not collision_times:
                collision_times = [samples[-1].timestamp]
            labels = generate_failure_labels(
                samples,
                config=rule_config,
                collision_times=collision_times,
                collision_lookahead_s=windows["offline_collision_lookahead_s"],
                pre_failure_window_s=windows["positive_pre_failure_window_s"],
                post_failure_window_s=windows["positive_post_failure_window_s"],
            )
            group = episodes.create_group(episode_id)
            group.create_dataset("timestamps", data=[sample.timestamp for sample in samples])
            group.create_dataset("failure", data=labels.failure, compression="gzip")
            group.create_dataset("failure_any", data=labels.failure_any, compression="gzip")
            group.create_dataset("time_to_failure", data=labels.time_to_failure, compression="gzip")
            group.create_dataset("failure_onset", data=labels.failure_onset, compression="gzip")
            group.create_dataset("failure_end", data=labels.failure_end, compression="gzip")
            group.attrs["scenario_id"] = record["scenario_id"]
            group.attrs["family"] = record["family"]
            group.attrs["seed"] = int(record["seed"])
            group.attrs["outcome"] = record["outcome"]

            total_class_counts += labels.failure.sum(axis=0)
            onset_counts[record["family"]] += int(labels.failure_onset.sum())
            hard_negative_count += sum(
                not labels.failure_any[index]
                and (
                    sample.nearest_lidar_distance < 2.0
                    or sample.planner_status
                    in {PlannerStatus.NO_VALID_CONTROL, PlannerStatus.ABORTED}
                )
                for index, sample in enumerate(samples)
            )
            total_samples += len(samples)

    summary = {
        "schema_version": 1,
        "episode_count": len(records),
        "sample_count": total_samples,
        "positive_counts": {
            failure_type.name: int(total_class_counts[failure_type]) for failure_type in FailureType
        },
        "failure_onsets_by_family": dict(sorted(onset_counts.items())),
        "hard_negative_count": hard_negative_count,
        "config": str(config_path.relative_to(ROOT)),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "labels_hdf5": str(destination.relative_to(ROOT)),
        "labels_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "baseline_failure_mining.csv",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "failure" / "rules.yaml")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "interim" / "gate1_failure_labels.h5",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "data" / "manifests" / "failure_label_summary.json",
    )
    args = parser.parse_args()
    summary = label_dataset(
        args.results.resolve(),
        args.config.resolve(),
        args.output.resolve(),
        args.summary.resolve(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
