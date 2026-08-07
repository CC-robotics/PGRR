#!/usr/bin/env python3
"""Summarize valid Gate 1 outcomes and separately report invalid reset attempts."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EPISODE_PATTERN = re.compile(
    r"(head_on_corridor|doorway_bottleneck|crossing_flow)_high_mining_seed\d+_base_dwb"
)


def summarize(results_path: Path, destination: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(results_path.open(encoding="utf-8")))
    if not rows:
        raise ValueError("failure-mining results are empty")
    if len({row["episode_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate episode IDs in failure-mining results")
    families: dict[str, Any] = {}
    for family in sorted({row["family"] for row in rows}):
        selected = [row for row in rows if row["family"] == family]
        counts = Counter(row["outcome"] for row in selected)
        failures = sum(row["outcome"] != "GOAL_REACHED" for row in selected)
        families[family] = {
            "episode_count": len(selected),
            "outcomes": dict(sorted(counts.items())),
            "failure_count": failures,
            "failure_rate": failures / len(selected),
        }

    invalid_resets: list[dict[str, Any]] = []
    reset_root = ROOT / "outputs" / "logs" / "baseline" / "invalid_reset"
    for path in sorted(reset_root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["diagnostic"] = str(path.relative_to(ROOT))
        invalid_resets.append(record)
    interrupted = ROOT / "outputs" / "logs" / "baseline" / "interrupted"
    legacy_logs = sorted(interrupted.glob("parallel_*runtime.log")) + sorted(
        interrupted.glob("invalid_reset_*runtime.log")
    )
    for path in legacy_logs:
        match = EPISODE_PATTERN.search(path.name)
        invalid_resets.append(
            {
                "episode_id": match.group(0) if match else "unknown",
                "outcome": "INVALID_RESET",
                "exclusion_reason": "Arena/Nav2 action did not become ready",
                "diagnostic": str(path.relative_to(ROOT)),
            }
        )

    payload = {
        "schema_version": 1,
        "purpose": "Gate 1 train-split deterministic failure reproduction",
        "algorithm_episode_count": len(rows),
        "total_sample_count": sum(int(row["sample_count"]) for row in rows),
        "unique_raw_hash_count": len({row["raw_sha256"] for row in rows}),
        "families": families,
        "excluded_invalid_reset_count": len(invalid_resets),
        "invalid_resets": invalid_resets,
        "source_results": str(results_path.relative_to(ROOT)),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "baseline_failure_mining.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "pilot" / "baseline_failure_summary.json",
    )
    args = parser.parse_args()
    payload = summarize(args.results.resolve(), args.output.resolve())
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
