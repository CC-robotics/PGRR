#!/usr/bin/env python3
"""Convert one or more raw JSONL episode streams into a validated HDF5 shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.data.hdf5 import validate_file, write_episode
from ramp_core.data.schema import EpisodeMetadata, EpisodeOutcome, NavigationStep


def _prefix(path: Path) -> Path:
    return path.with_suffix("") if path.suffix == ".jsonl" else path


def _load_step(record: dict[str, Any]) -> NavigationStep:
    return NavigationStep(
        timestamp=float(record["timestamp"]),
        robot_pose=np.asarray(record["robot_pose"]),
        robot_velocity=np.asarray(record["robot_velocity"]),
        cmd_vel=np.asarray(record["cmd_vel"]),
        base_cmd_vel=np.asarray(record["base_cmd_vel"]),
        goal=np.asarray(record["goal"]),
        distance_to_goal=float(record["distance_to_goal"]),
        global_path=tuple(
            tuple(float(value) for value in point) for point in record["global_path"]
        ),
        lidar=np.asarray(record["lidar"]),
        nearest_obstacle_distance=float(record["nearest_obstacle_distance"]),
        planner_status=int(record["planner_status"]),
        recovery_state=int(record["recovery_state"]),
        recovery_action=int(record["recovery_action"]),
        collision=bool(record["collision"]),
        timeout=bool(record["timeout"]),
        privileged=dict(record["privileged"]),
    )


def convert(prefixes: list[Path], destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing shard: {destination}")
    for raw_prefix in prefixes:
        prefix = _prefix(raw_prefix)
        stream_path = prefix.with_suffix(".jsonl")
        metadata_path = prefix.with_suffix(".metadata.json")
        outcome_path = prefix.with_suffix(".outcome.json")
        for required in (stream_path, metadata_path, outcome_path):
            if not required.is_file():
                raise FileNotFoundError(required)
        metadata = EpisodeMetadata(**json.loads(metadata_path.read_text(encoding="utf-8")))
        outcome_payload = json.loads(outcome_path.read_text(encoding="utf-8"))
        outcome = EpisodeOutcome[outcome_payload["outcome"]]
        steps = [
            _load_step(json.loads(line))
            for line in stream_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        write_episode(destination, metadata, steps, outcome)
    return validate_file(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-prefix", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = convert(args.input_prefix, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
