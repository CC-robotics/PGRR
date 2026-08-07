#!/usr/bin/env python3
"""Extract one preregistered matched Base--PGRR run from hash-verified raw logs.

The selected condition is fixed before outcomes are inspected:
``doorway_bottleneck / medium / replicate 0``.  The emitted JSON is a compact,
self-contained reporting sidecar.  It records the source Parquet and raw-log
hashes and carries downsampled robot trajectories and event timelines.  It is
telemetry evidence, not a simulator-camera image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd

METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
SELECTOR = {"family": "doorway_bottleneck", "density": "medium", "replicate": 0}
MAX_SAMPLES = 480


class MatchedEvidenceError(RuntimeError):
    """Raised when matched evidence cannot be tied to complete v6 results."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: object, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MatchedEvidenceError(f"raw field {field!r} must be numeric") from error
    if not math.isfinite(number):
        raise MatchedEvidenceError(f"raw field {field!r} must be finite")
    return number


def _state(value: object) -> str:
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value)
    raise MatchedEvidenceError("raw recovery_state must be a non-empty string or integer")


def _action(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value)
    raise MatchedEvidenceError("raw recovery_action must be a string, integer, or null")


def _read_trace(path: Path) -> dict[str, list[Any]]:
    trace: dict[str, list[Any]] = {
        "time_s": [],
        "robot_x_m": [],
        "robot_y_m": [],
        "distance_to_goal_m": [],
        "failure_score": [],
        "recovery_state": [],
        "recovery_action": [],
    }
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise MatchedEvidenceError(
                    f"invalid JSON in {path.name} at line {line_number}"
                ) from error
            if not isinstance(record, Mapping):
                raise MatchedEvidenceError(f"raw line {line_number} must be a JSON object")
            pose = record.get("robot_pose")
            if not isinstance(pose, list) or len(pose) < 2:
                raise MatchedEvidenceError(
                    f"raw robot_pose at line {line_number} must contain x and y"
                )
            trace["time_s"].append(_finite(record.get("timestamp"), field="timestamp"))
            trace["robot_x_m"].append(_finite(pose[0], field="robot_pose[0]"))
            trace["robot_y_m"].append(_finite(pose[1], field="robot_pose[1]"))
            trace["distance_to_goal_m"].append(
                _finite(record.get("distance_to_goal"), field="distance_to_goal")
            )
            trace["failure_score"].append(
                _finite(record.get("failure_score"), field="failure_score")
            )
            trace["recovery_state"].append(_state(record.get("recovery_state")))
            trace["recovery_action"].append(_action(record.get("recovery_action")))

    sample_count = len(trace["time_s"])
    if sample_count < 2:
        raise MatchedEvidenceError(f"raw trace is too short: {path}")
    times = trace["time_s"]
    if any(float(right) < float(left) for left, right in pairwise(times)):
        raise MatchedEvidenceError(f"raw timestamps are not monotonic: {path}")
    if sample_count > MAX_SAMPLES:
        indices = sorted(
            {round(index * (sample_count - 1) / (MAX_SAMPLES - 1)) for index in range(MAX_SAMPLES)}
        )
        trace = {key: [values[index] for index in indices] for key, values in trace.items()}
    return trace


def _validate_results(results: pd.DataFrame, *, stage: str) -> pd.DataFrame:
    required = {
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "replicate",
        "seed",
        "split",
        "source_policy",
        "episode_id",
        "outcome",
        "raw_sha256",
        "scenario_sha256",
    }
    missing = sorted(required - set(results.columns))
    if missing:
        raise MatchedEvidenceError(f"results.parquet is missing columns: {missing}")
    if set(results["split"].astype(str)) != {stage}:
        raise MatchedEvidenceError(f"evidence stage {stage!r} does not match results split")
    if set(results["source_policy"].astype(str)) != set(METHODS):
        raise MatchedEvidenceError("matched evidence requires the complete five-method result")
    if not bool(results["scenario_id"].astype(str).str.contains("_moderate_v6_").all()):
        raise MatchedEvidenceError("matched evidence accepts only moderate-v6 scenario IDs")
    expected_conditions = 72 if stage == "validation" else 120
    if results["pair_id"].nunique() != expected_conditions:
        raise MatchedEvidenceError(
            f"stage {stage!r} requires {expected_conditions} complete paired conditions"
        )
    chosen = results.loc[
        (results["family"].astype(str) == SELECTOR["family"])
        & (results["density"].astype(str) == SELECTOR["density"])
        & (pd.to_numeric(results["replicate"], errors="coerce") == SELECTOR["replicate"])
        & results["source_policy"].isin(("base", "pgrr"))
    ].copy()
    if len(chosen) != 2 or set(chosen["source_policy"].astype(str)) != {"base", "pgrr"}:
        raise MatchedEvidenceError(
            "fixed matched selector does not resolve one Base and one PGRR row"
        )
    if chosen["pair_id"].astype(str).nunique() != 1:
        raise MatchedEvidenceError("fixed Base and PGRR rows do not share the same pair_id")
    return chosen.sort_values("source_policy")


def build_evidence(
    *,
    stage: str,
    results_path: Path,
    raw_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    if stage not in {"validation", "test"}:
        raise MatchedEvidenceError("stage must be validation or test")
    if not results_path.is_file():
        raise MatchedEvidenceError(f"results file is missing: {results_path}")
    if not raw_dir.is_dir():
        raise MatchedEvidenceError(f"raw directory is missing: {raw_dir}")
    results = pd.read_parquet(results_path)
    chosen = _validate_results(results, stage=stage)
    runs: dict[str, Any] = {}
    for _, row in chosen.iterrows():
        method = str(row["source_policy"])
        raw_path = raw_dir / f"{row['episode_id']}.jsonl"
        if not raw_path.is_file():
            raise MatchedEvidenceError(f"matched raw log is missing: {raw_path.name}")
        raw_sha256 = _sha256(raw_path)
        if raw_sha256 != str(row["raw_sha256"]):
            raise MatchedEvidenceError(f"raw SHA256 disagrees with Parquet for {method}")
        trace = _read_trace(raw_path)
        runs[method] = {
            "episode_id": str(row["episode_id"]),
            "outcome": str(row["outcome"]),
            "raw_file": raw_path.name,
            "raw_sha256": raw_sha256,
            "sample_count_exported": len(trace["time_s"]),
            "trace": trace,
        }
    first = chosen.iloc[0]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "matched_base_pgrr_raw_telemetry",
        "benchmark_id": "moderate_social_navigation_v6",
        "stage": stage,
        "selection_rule": "doorway_bottleneck/medium/replicate-0; outcome-independent",
        "selector": dict(SELECTOR),
        "pair_id": str(first["pair_id"]),
        "scenario_id": str(first["scenario_id"]),
        "scenario_sha256": str(first["scenario_sha256"]),
        "seed": int(first["seed"]),
        "results_file": results_path.name,
        "results_sha256": _sha256(results_path),
        "representation": "telemetry reconstruction; not a simulator camera screenshot",
        "runs": runs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("validation", "test"), required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_evidence(
            stage=args.stage,
            results_path=args.results,
            raw_dir=args.raw_dir,
            output_path=args.output,
        )
    except (MatchedEvidenceError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "Matched evidence PASS: "
        f"pair={payload['pair_id']}, output={args.output}, representation=telemetry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
