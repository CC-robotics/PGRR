#!/usr/bin/env python3
"""Summarize small repeated-method pilots without overstating significance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import beta, fisher_exact  # type: ignore[import-untyped]


def exact_binomial_interval(successes: int, total: int, confidence: float = 0.95) -> list[float]:
    if total <= 0 or not 0 <= successes <= total or not 0.0 < confidence < 1.0:
        raise ValueError("invalid binomial interval inputs")
    alpha = 1.0 - confidence
    lower = (
        0.0 if successes == 0 else float(beta.ppf(alpha / 2.0, successes, total - successes + 1))
    )
    upper = (
        1.0
        if successes == total
        else float(beta.ppf(1.0 - alpha / 2.0, successes + 1, total - successes))
    )
    return [lower, upper]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    frame = pd.read_csv(args.input)
    if set(frame["source_policy"]) != {"base", "bc"}:
        raise ValueError("pilot CSV must contain exactly base and bc policies")
    payload: dict[str, object] = {"schema_version": 1, "input": str(args.input), "methods": {}}
    method_payload: dict[str, object] = {}
    for method, rows in frame.groupby("source_policy", sort=True):
        successes = int((rows["outcome"] == "GOAL_REACHED").sum())
        collisions = int((rows["outcome"] == "COLLISION").sum())
        total = len(rows)
        successful_times = rows.loc[rows["outcome"] == "GOAL_REACHED", "sim_duration_s"]
        method_payload[str(method)] = {
            "episode_count": total,
            "outcome_counts": rows["outcome"].value_counts().sort_index().to_dict(),
            "success_rate": successes / total,
            "success_rate_95pct_clopper_pearson": exact_binomial_interval(successes, total),
            "collision_rate": collisions / total,
            "median_min_human_distance_m": float(rows["min_human_distance_m"].median()),
            "median_success_time_s": (
                None if successful_times.empty else float(successful_times.median())
            ),
        }
    payload["methods"] = method_payload
    base = method_payload["base"]
    learned = method_payload["bc"]
    table = [
        [
            base["outcome_counts"].get("GOAL_REACHED", 0),
            base["episode_count"] - base["outcome_counts"].get("GOAL_REACHED", 0),
        ],
        [
            learned["outcome_counts"].get("GOAL_REACHED", 0),
            learned["episode_count"] - learned["outcome_counts"].get("GOAL_REACHED", 0),
        ],
    ]
    fisher = fisher_exact(table, alternative="two-sided")
    payload["unpaired_fisher_success"] = {
        "odds_ratio": float(fisher.statistic),
        "pvalue_two_sided": float(fisher.pvalue),
    }
    payload["warning"] = (
        "Repeated same-seed pilot with residual Gazebo scheduling variance; "
        "not final paired multi-seed evidence."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
