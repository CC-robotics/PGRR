#!/usr/bin/env python3
"""Apply the observable recovery-cycle contract to existing PGRR JSONL logs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ramp_core.recovery.progress import (
    RecoveryCycleEvidence,
    RecoveryCycleProgressConfig,
    assess_recovery_cycle,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cycle_bounds(rows: list[dict[str, Any]]) -> list[tuple[int, int, bool]]:
    bounds: list[tuple[int, int, bool]] = []
    start: int | None = None
    for index, row in enumerate(rows):
        state = int(row.get("recovery_state", 0))
        previous = int(rows[index - 1].get("recovery_state", 0)) if index else 0
        if state != 0 and previous == 0:
            start = index
        if state == 0 and previous != 0 and start is not None:
            bounds.append((start, index, True))
            start = None
    if start is not None:
        bounds.append((start, len(rows) - 1, False))
    return bounds


def _goal_distance(row: dict[str, Any], original_goal: list[float]) -> float:
    pose = row["robot_pose"]
    return math.hypot(float(pose[0]) - original_goal[0], float(pose[1]) - original_goal[1])


def _clear_frames(rows: list[dict[str, Any]], end: int, threshold: float) -> int:
    count = 0
    for row in reversed(rows[: end + 1]):
        if float(row.get("failure_score", 1.0)) > threshold:
            break
        count += 1
    return count


def adapt_episode(
    rows: list[dict[str, Any]],
    config: RecoveryCycleProgressConfig,
    *,
    clear_failure_score_threshold: float,
    original_goal_tolerance_m: float,
) -> list[dict[str, Any]]:
    if len(rows) < 2:
        raise ValueError("episode must contain at least two samples")
    if not 0.0 <= clear_failure_score_threshold <= 1.0:
        raise ValueError("clear failure-score threshold must lie in [0, 1]")
    if not math.isfinite(original_goal_tolerance_m) or original_goal_tolerance_m < 0.0:
        raise ValueError("original-goal tolerance must be finite and non-negative")

    original_goal = [float(value) for value in rows[0]["goal"]]
    bounds = _cycle_bounds(rows)
    output = []
    for cycle_index, (start, end, completed) in enumerate(bounds, start=1):
        next_start = bounds[cycle_index][0] if cycle_index < len(bounds) else None
        end_time = float(rows[end]["timestamp"])
        if next_start is not None:
            retrigger_delay = float(rows[next_start]["timestamp"]) - end_time
            retrigger_observation = retrigger_delay
        else:
            retrigger_delay = None
            retrigger_observation = float(rows[-1]["timestamp"]) - end_time

        active_goal = [float(value) for value in rows[end]["goal"]]
        original_goal_active = (
            math.hypot(active_goal[0] - original_goal[0], active_goal[1] - original_goal[1])
            <= original_goal_tolerance_m
        )
        evidence = RecoveryCycleEvidence(
            start_original_goal_distance_m=_goal_distance(rows[start], original_goal),
            end_original_goal_distance_m=_goal_distance(rows[end], original_goal),
            consecutive_clear_frames=_clear_frames(
                rows, end, clear_failure_score_threshold
            ),
            original_goal_active=original_goal_active,
            retrigger_delay_s=retrigger_delay,
            retrigger_observation_s=max(0.0, retrigger_observation),
        )
        assessment = assess_recovery_cycle(evidence, config)
        output.append(
            {
                "cycle_index": cycle_index,
                "start_sample": start,
                "end_sample": end,
                "cycle_completed_to_normal": completed,
                **asdict(evidence),
                **asdict(assessment),
                "verdict": assessment.verdict.value,
            }
        )
    return output


def adapt_pilot(
    progress_path: Path,
    data_root: Path,
    config: RecoveryCycleProgressConfig,
    *,
    clear_failure_score_threshold: float,
    original_goal_tolerance_m: float,
) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    cycles = []
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        if _sha256(path) != run["artifact_sha256"]["raw_jsonl"]:
            raise ValueError(f"raw log hash mismatch: {path}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        episode_cycles = adapt_episode(
            rows,
            config,
            clear_failure_score_threshold=clear_failure_score_threshold,
            original_goal_tolerance_m=original_goal_tolerance_m,
        )
        for cycle in episode_cycles:
            cycle.update(
                {
                    "family_index": pair["family_index"],
                    "family": pair["family"],
                    "episode_id": episode_id,
                }
            )
        cycles.extend(episode_cycles)

    aggregate = {
        "cycle_count": len(cycles),
        "raw_hashes_verified": True,
        "verdict_counts": dict(sorted(Counter(row["verdict"] for row in cycles).items())),
        "hazard_cleared_count": sum(row["hazard_cleared"] for row in cycles),
        "meaningful_task_progress_count": sum(
            row["meaningful_task_progress"] for row in cycles
        ),
        "rapid_retrigger_count": sum(row["rapid_retrigger"] for row in cycles),
        "retrigger_observation_complete_count": sum(
            row["retrigger_observation_complete"] for row in cycles
        ),
        "original_goal_active_count": sum(row["original_goal_active"] for row in cycles),
        "maximum_cycle_progress_m": round(
            max(row["original_goal_progress_m"] for row in cycles), 6
        ),
        "median_cycle_progress_m": round(
            statistics.median(row["original_goal_progress_m"] for row in cycles), 6
        ),
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "train_only_contract_probe_not_runtime_configuration",
        "config": asdict(config),
        "clear_failure_score_threshold": clear_failure_score_threshold,
        "original_goal_tolerance_m": original_goal_tolerance_m,
        "aggregate": aggregate,
        "cycles": cycles,
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = report["cycles"]
    if not rows:
        raise ValueError("no recovery cycles were adapted")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--minimum-progress-m", type=float, required=True)
    parser.add_argument("--minimum-clear-frames", type=int, required=True)
    parser.add_argument("--rapid-retrigger-window-s", type=float, required=True)
    parser.add_argument("--clear-failure-score-threshold", type=float, required=True)
    parser.add_argument("--original-goal-tolerance-m", type=float, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    config = RecoveryCycleProgressConfig(
        minimum_original_goal_progress_m=args.minimum_progress_m,
        minimum_clear_frames=args.minimum_clear_frames,
        rapid_retrigger_window_s=args.rapid_retrigger_window_s,
    )
    report = adapt_pilot(
        args.progress,
        args.data_root,
        config,
        clear_failure_score_threshold=args.clear_failure_score_threshold,
        original_goal_tolerance_m=args.original_goal_tolerance_m,
    )
    write_outputs(report, args.json_output, args.csv_output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
