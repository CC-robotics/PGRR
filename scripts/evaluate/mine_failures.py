#!/usr/bin/env python3
"""Run or resume the fixed Gate 1 failure-mining manifest and summarize every outcome."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
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
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def _archive_invalid_reset(episode_id: str, attempt: int, returncode: int) -> Path:
    archive_root = ROOT / "outputs" / "logs" / "baseline" / "invalid_reset"
    archive_root.mkdir(parents=True, exist_ok=True)
    raw_archive = ROOT / "data" / "raw" / "invalid_reset"
    raw_archive.mkdir(parents=True, exist_ok=True)
    for kind in ("runtime", "status"):
        source = ROOT / "outputs" / "logs" / "baseline" / f"{episode_id}_{kind}.log"
        if source.exists():
            source.replace(archive_root / f"{episode_id}_attempt{attempt:02d}_{kind}.log")
    for suffix in ("jsonl", "metadata.json", "outcome.json"):
        source = ROOT / "data" / "raw" / f"{episode_id}.{suffix}"
        if source.exists():
            source.replace(raw_archive / f"{episode_id}_attempt{attempt:02d}.{suffix}")
    diagnostic = {
        "episode_id": episode_id,
        "attempt": attempt,
        "outcome": "INVALID_RESET",
        "returncode": returncode,
        "timestamp": datetime.now(UTC).isoformat(),
        "exclusion_reason": "Arena/Nav2 did not produce a valid terminal episode",
    }
    destination = archive_root / f"{episode_id}_attempt{attempt:02d}.json"
    destination.write_text(
        json.dumps(diagnostic, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def run(
    manifest_path: Path,
    output: Path,
    limit: int | None,
    family: str | None = None,
    max_reset_retries: int = 2,
) -> None:
    if max_reset_retries < 0:
        raise ValueError("max_reset_retries must be non-negative")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    records = list(manifest["episodes"])
    if family is not None:
        records = [record for record in records if record["family"] == family]
        if not records:
            raise ValueError(f"manifest has no episodes for family: {family}")
    if limit is not None:
        records = records[:limit]
    summaries: list[dict[str, Any]] = []
    domain_base = int(os.environ.get("RAMP_ROS_DOMAIN_BASE", "20"))
    partition_base = os.environ.get("RAMP_GZ_PARTITION_BASE", "ramp_mining")
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
            for attempt in range(max_reset_retries + 1):
                environment["ROS_DOMAIN_ID"] = str(
                    domain_base + int(record["seed"]) * (max_reset_retries + 1) + attempt
                )
                environment["GZ_PARTITION"] = (
                    f"{partition_base}_{record['family']}_{record['seed']}_a{attempt}"
                )
                environment["IGN_PARTITION"] = environment["GZ_PARTITION"]
                completed = subprocess.run(
                    [
                        str(ROOT / "scripts" / "arena" / "run_baseline_episode.sh"),
                        str(scenario_path),
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                )
                if completed.returncode == 0:
                    break
                diagnostic = _archive_invalid_reset(episode_id, attempt, completed.returncode)
                print(
                    f"[{index}/{len(records)}] INVALID_RESET attempt={attempt} "
                    f"diagnostic={diagnostic}",
                    flush=True,
                )
            else:
                raise RuntimeError(
                    f"episode exhausted {max_reset_retries + 1} reset attempts: {episode_id}"
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
    parser.add_argument(
        "--family",
        choices=("head_on_corridor", "doorway_bottleneck", "crossing_flow"),
    )
    parser.add_argument("--max-reset-retries", type=int, default=2)
    args = parser.parse_args()
    run(
        args.manifest.resolve(),
        args.output.resolve(),
        args.limit,
        args.family,
        args.max_reset_retries,
    )


if __name__ == "__main__":
    main()
