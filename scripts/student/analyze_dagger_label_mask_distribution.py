#!/usr/bin/env python3
"""Read-only DAgger label and action-mask distribution audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import h5py
import numpy as np

ACTION_NAMES = {
    **{index: f"SUBGOAL_{index}" for index in range(21)},
    21: "WAIT",
    22: "BACKUP",
    23: "REPLAN",
    24: "CONTINUE",
}
FAILURE_NAMES = ("COLLISION_RISK", "FREEZE", "OSCILLATION", "DEADLOCK")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_dataset(
    path: Path, name: str, *, expected_sha256: str | None = None
) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        actions = np.asarray(handle["labels/expert_action"][:], dtype=np.int64)
        masks = np.asarray(handle["labels/action_mask"][:], dtype=bool)
        margins = np.asarray(handle["labels/expert_margin"][:], dtype=np.float64)
        success = np.asarray(handle["labels/predicted_success"][:], dtype=np.float64)
        sample_index = np.asarray(handle["sample_index"][:], dtype=np.int64)
        failures = np.asarray(handle["observations/failure_prediction"][:], dtype=np.float64)[
            sample_index
        ]
        episode_starts = np.asarray(
            handle["observations/episode_start_index"][:], dtype=np.int64
        )

    if masks.shape != (len(actions), 25):
        raise ValueError(f"unexpected action-mask shape: {masks.shape}")
    if np.any(actions < 0) or np.any(actions >= 25):
        raise ValueError("expert action lies outside the 25-action space")
    permitted = masks[np.arange(len(actions)), actions]
    counts = Counter(ACTION_NAMES[int(value)] for value in actions)
    valid_counts = masks.sum(axis=1)
    dominant = np.argmax(failures, axis=1)
    zero_signal = np.max(failures, axis=1) == 0.0
    failure_counts = Counter(FAILURE_NAMES[int(value)] for value in dominant[~zero_signal])
    failure_counts["NO_POSITIVE_SIGNAL"] = int(np.count_nonzero(zero_signal))
    unique_episode_starts = np.unique(episode_starts[sample_index])
    actual_sha256 = _sha256(path)
    return {
        "name": name,
        "path": path.as_posix(),
        "sha256": actual_sha256,
        "expected_sha256": expected_sha256,
        "sha256_matches_expected": (
            None if expected_sha256 is None else actual_sha256 == expected_sha256.lower()
        ),
        "sample_count": len(actions),
        "episode_count": len(unique_episode_starts),
        "expert_action_counts": dict(sorted(counts.items())),
        "action_group_counts": {
            "temporary_subgoal": int(np.count_nonzero(actions <= 20)),
            "wait": int(np.count_nonzero(actions == 21)),
            "backup": int(np.count_nonzero(actions == 22)),
            "replan": int(np.count_nonzero(actions == 23)),
            "continue": int(np.count_nonzero(actions == 24)),
        },
        "expert_action_permitted_count": int(np.count_nonzero(permitted)),
        "expert_action_permitted_fraction": float(np.mean(permitted)),
        "valid_action_count": {
            "minimum": int(np.min(valid_counts)),
            "median": float(np.median(valid_counts)),
            "mean": float(np.mean(valid_counts)),
            "maximum": int(np.max(valid_counts)),
        },
        "expert_margin": {
            "median": float(np.median(margins)),
            "q10": float(np.quantile(margins, 0.1)),
            "q90": float(np.quantile(margins, 0.9)),
        },
        "predicted_success_fraction": float(np.mean(success > 0.5)),
        "dominant_failure_counts": dict(sorted(failure_counts.items())),
    }


def build_report(
    named_paths: list[tuple[str, Path]], expected_hashes: dict[str, str] | None = None
) -> dict[str, Any]:
    if not named_paths:
        raise ValueError("at least one dataset is required")
    datasets = [
        audit_dataset(
            path,
            name,
            expected_sha256=(expected_hashes or {}).get(name),
        )
        for name, path in named_paths
    ]
    checked = [
        item["sha256_matches_expected"]
        for item in datasets
        if item["sha256_matches_expected"] is not None
    ]
    return {
        "schema_version": 1,
        "claim_boundary": "read_only_distribution_diagnostic_not_overfitting_proof",
        "all_expected_hashes_match": bool(checked) and all(checked),
        "canonical_comparison_ready": bool(checked) and all(checked),
        "datasets": datasets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        action="append",
        nargs=2,
        metavar=("NAME", "PATH"),
        required=True,
    )
    parser.add_argument(
        "--expected-sha256",
        action="append",
        nargs=2,
        metavar=("NAME", "SHA256"),
        default=[],
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = {name: value.lower() for name, value in args.expected_sha256}
    report = build_report(
        [(name, Path(path)) for name, path in args.dataset], expected
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
