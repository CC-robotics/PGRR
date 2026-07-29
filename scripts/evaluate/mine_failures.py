#!/usr/bin/env python3
"""Run or resume the fixed Gate 1 failure-mining manifest and summarize every outcome."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_OUTCOMES = {
    "GOAL_REACHED",
    "COLLISION",
    "TIMEOUT",
    "PLANNER_FAILURE",
    "SIMULATOR_FAILURE",
    "INVALID_RESET",
}


def _summarize(prefix: Path, record: dict[str, Any]) -> dict[str, Any]:
    outcome_path = prefix.with_suffix(".outcome.json")
    stream_path = prefix.with_suffix(".jsonl")
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    if outcome["outcome"] not in ALLOWED_OUTCOMES:
        raise ValueError(f"unknown outcome in {outcome_path}")
    rows = [json.loads(line) for line in stream_path.read_text(encoding="utf-8").splitlines()]
    if not rows:
        raise ValueError(f"empty episode stream: {stream_path}")
    human_distances = [
        float(row["privileged"].get("nearest_human_distance", float("inf"))) for row in rows
    ]
    return {
        "episode_id": prefix.name,
        "scenario_id": record["scenario_id"],
        "family": record["family"],
        "density": record["density"],
        "seed": record["seed"],
        "planner_id": "dwb",
        "outcome": outcome["outcome"],
        "sample_count": len(rows),
        "sim_duration_s": float(rows[-1]["timestamp"]),
        "start_distance_m": float(rows[0]["distance_to_goal"]),
        "end_distance_m": float(rows[-1]["distance_to_goal"]),
        "progress_m": float(rows[0]["distance_to_goal"] - rows[-1]["distance_to_goal"]),
        "min_human_distance_m": min(human_distances),
        "min_lidar_m": min(float(row["nearest_obstacle_distance"]) for row in rows),
        "raw_sha256": hashlib.sha256(stream_path.read_bytes()).hexdigest(),
    }


def _write_csv(destination: Path, rows: list[dict[str, Any]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def run(manifest_path: Path, output: Path, limit: int | None) -> None:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    records = list(manifest["episodes"])
    if limit is not None:
        records = records[:limit]
    summaries: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        scenario_path = ROOT / record["path"]
        episode_id = f"{record['scenario_id']}_base_dwb"
        prefix = ROOT / "data" / "raw" / episode_id
        if not prefix.with_suffix(".outcome.json").exists():
            print(f"[{index}/{len(records)}] RUN {episode_id}", flush=True)
            environment = os.environ.copy()
            environment.pop("CONDA_PREFIX", None)
            environment.pop("VIRTUAL_ENV", None)
            environment["RAMP_EPISODE_ID"] = episode_id
            environment["RAMP_EPISODE_TIMEOUT_S"] = str(record["timeout_s"])
            subprocess.run(
                [str(ROOT / "scripts" / "arena" / "run_baseline_episode.sh"), str(scenario_path)],
                cwd=ROOT,
                env=environment,
                check=True,
            )
        else:
            print(f"[{index}/{len(records)}] RESUME {episode_id}", flush=True)
        summaries.append(_summarize(prefix, record))
        _write_csv(output, summaries)
    print(f"Failure-mining summary: {output} ({len(summaries)} episodes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "scenarios" / "manifests" / "failure_mining.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "baseline_failure_mining.csv",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(args.manifest.resolve(), args.output.resolve(), args.limit)


if __name__ == "__main__":
    main()
