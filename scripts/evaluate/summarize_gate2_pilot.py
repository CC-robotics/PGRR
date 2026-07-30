#!/usr/bin/env python3
"""Generate an auditable paired Gate 2 comparison from episode CSV files."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.evaluation.statistics import (
    bootstrap_paired_difference,
    exact_mcnemar,
    paired_wilcoxon,
)

ROOT = Path(__file__).resolve().parents[2]
ALGORITHM_OUTCOMES = {
    "GOAL_REACHED",
    "COLLISION",
    "TIMEOUT",
    "PLANNER_FAILURE",
}


def _load(paths: list[Path], expected_policy: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            rows.extend(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"no {expected_policy} rows")
    if any(row["source_policy"] != expected_policy for row in rows):
        raise ValueError(f"input contains rows outside policy {expected_policy}")
    if any(row["outcome"] not in ALGORITHM_OUTCOMES for row in rows):
        raise ValueError("simulator failures and invalid resets cannot be algorithm rows")
    keys = [(row["scenario_id"], int(row["seed"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate {expected_policy} episode pair keys")
    return rows


def _policy_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    outcomes = Counter(row["outcome"] for row in rows)
    progress = np.array([float(row["progress_m"]) for row in rows])
    human_distance = np.array([float(row["min_human_distance_m"]) for row in rows])
    return {
        "episode_count": len(rows),
        "outcomes": dict(sorted(outcomes.items())),
        "success_rate": outcomes["GOAL_REACHED"] / len(rows),
        "collision_rate": outcomes["COLLISION"] / len(rows),
        "timeout_rate": outcomes["TIMEOUT"] / len(rows),
        "mean_progress_m": float(progress.mean()),
        "median_progress_m": float(np.median(progress)),
        "mean_min_human_distance_m": float(human_distance.mean()),
        "median_min_human_distance_m": float(np.median(human_distance)),
    }


def _matching_invalid_resets(episode_ids: set[str], root: Path) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("episode_id") in episode_ids:
            diagnostics.append({**record, "diagnostic": str(path)})
    return diagnostics


def summarize(
    base_paths: list[Path],
    heuristic_paths: list[Path],
    json_output: Path,
    csv_output: Path,
    *,
    seed: int,
    bootstrap_samples: int,
    standard_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate episode pairing, compute statistics, and write JSON/CSV outputs."""
    base = _load(base_paths, "base")
    heuristic = _load(heuristic_paths, "heuristic")
    standard = _load(standard_paths, "standard") if standard_paths else []
    base_by_key = {(row["scenario_id"], int(row["seed"])): row for row in base}
    heuristic_by_key = {(row["scenario_id"], int(row["seed"])): row for row in heuristic}
    if base_by_key.keys() != heuristic_by_key.keys():
        missing_base = sorted(heuristic_by_key.keys() - base_by_key.keys())
        missing_heuristic = sorted(base_by_key.keys() - heuristic_by_key.keys())
        raise ValueError(
            "unpaired manifests: "
            f"missing_base={missing_base}, missing_heuristic={missing_heuristic}"
        )
    keys = sorted(base_by_key)
    standard_by_key = {(row["scenario_id"], int(row["seed"])): row for row in standard}
    if standard_by_key and standard_by_key.keys() != base_by_key.keys():
        raise ValueError("standard baseline is not paired to the base manifest")
    base_progress = np.array([float(base_by_key[key]["progress_m"]) for key in keys])
    heuristic_progress = np.array([float(heuristic_by_key[key]["progress_m"]) for key in keys])
    base_collision = np.array(
        [base_by_key[key]["outcome"] == "COLLISION" for key in keys], dtype=np.int8
    )
    heuristic_collision = np.array(
        [heuristic_by_key[key]["outcome"] == "COLLISION" for key in keys], dtype=np.int8
    )
    progress_ci = bootstrap_paired_difference(
        base_progress,
        heuristic_progress,
        seed=seed,
        samples=bootstrap_samples,
    )
    collision_ci = bootstrap_paired_difference(
        base_collision,
        heuristic_collision,
        seed=seed + 1,
        samples=bootstrap_samples,
    )
    episode_ids = {row["episode_id"] for row in base + standard + heuristic}
    invalid_resets = _matching_invalid_resets(
        episode_ids, ROOT / "outputs" / "logs" / "baseline" / "invalid_reset"
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "Gate 2 paired train-split pilot; not final test evidence",
        "pair_count": len(keys),
        "families": sorted({key[0].rsplit("_high_mining_seed", 1)[0] for key in keys}),
        "base": _policy_summary(base),
        "heuristic": _policy_summary(heuristic),
        "paired_statistics": {
            "collision_mcnemar_exact": exact_mcnemar(base_collision, heuristic_collision),
            "collision_rate_difference_heuristic_minus_base": collision_ci.__dict__,
            "progress_difference_m_heuristic_minus_base": progress_ci.__dict__,
            "progress_wilcoxon": paired_wilcoxon(base_progress, heuristic_progress),
        },
        "excluded_invalid_reset_count": len(invalid_resets),
        "invalid_resets": invalid_resets,
        "bootstrap": {"samples": bootstrap_samples, "seed": seed, "confidence": 0.95},
        "source_files": {
            "base": [str(path) for path in base_paths],
            "heuristic": [str(path) for path in heuristic_paths],
        },
    }
    if standard_by_key:
        standard_progress = np.array([float(standard_by_key[key]["progress_m"]) for key in keys])
        standard_collision = np.array(
            [standard_by_key[key]["outcome"] == "COLLISION" for key in keys],
            dtype=np.int8,
        )
        standard_progress_ci = bootstrap_paired_difference(
            base_progress,
            standard_progress,
            seed=seed + 2,
            samples=bootstrap_samples,
        )
        standard_collision_ci = bootstrap_paired_difference(
            base_collision,
            standard_collision,
            seed=seed + 3,
            samples=bootstrap_samples,
        )
        payload["standard"] = _policy_summary(standard)
        payload["paired_statistics"].update(
            {
                "collision_mcnemar_exact_standard_vs_base": exact_mcnemar(
                    base_collision, standard_collision
                ),
                "collision_rate_difference_standard_minus_base": (standard_collision_ci.__dict__),
                "progress_difference_m_standard_minus_base": standard_progress_ci.__dict__,
                "progress_wilcoxon_standard_vs_base": paired_wilcoxon(
                    base_progress, standard_progress
                ),
            }
        )
        payload["source_files"]["standard"] = [str(path) for path in standard_paths or []]
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    with csv_output.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "scenario_id",
            "seed",
            "base_outcome",
            "standard_outcome",
            "heuristic_outcome",
            "base_progress_m",
            "standard_progress_m",
            "heuristic_progress_m",
            "base_min_human_distance_m",
            "standard_min_human_distance_m",
            "heuristic_min_human_distance_m",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for key in keys:
            reference = base_by_key[key]
            treatment = heuristic_by_key[key]
            standard_row = standard_by_key.get(key)
            writer.writerow(
                {
                    "scenario_id": key[0],
                    "seed": key[1],
                    "base_outcome": reference["outcome"],
                    "standard_outcome": standard_row["outcome"] if standard_row else "",
                    "heuristic_outcome": treatment["outcome"],
                    "base_progress_m": reference["progress_m"],
                    "standard_progress_m": standard_row["progress_m"] if standard_row else "",
                    "heuristic_progress_m": treatment["progress_m"],
                    "base_min_human_distance_m": reference["min_human_distance_m"],
                    "standard_min_human_distance_m": (
                        standard_row["min_human_distance_m"] if standard_row else ""
                    ),
                    "heuristic_min_human_distance_m": treatment["min_human_distance_m"],
                }
            )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, action="append", required=True)
    parser.add_argument("--standard", type=Path, action="append")
    parser.add_argument("--heuristic", type=Path, action="append", required=True)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "heuristic_comparison.json",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "heuristic_comparison.csv",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    args = parser.parse_args()
    payload = summarize(
        [path.resolve() for path in args.base],
        [path.resolve() for path in args.heuristic],
        args.json_output.resolve(),
        args.csv_output.resolve(),
        seed=args.seed,
        bootstrap_samples=args.bootstrap_samples,
        standard_paths=[path.resolve() for path in args.standard] if args.standard else None,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
