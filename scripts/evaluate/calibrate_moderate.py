#!/usr/bin/env python3
"""Build or verify the complete Base-only moderate-v6 calibration report.

Build mode accepts one collected validation Parquet and intentionally exposes no
family, density, scenario, seed, or outcome filters.  Verification mode checks
the accepted report against the path and SHA256 frozen in the final evaluation
configuration without opening the held-out test manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import summarize_moderate as moderate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = Path("outputs/moderate/v6_validation_base_d5fa66b/results.parquet")
DEFAULT_SPLIT_MANIFEST = Path("scenarios/splits/moderate_v6_validation.yaml")
DEFAULT_REPORT = Path("outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json")
DEFAULT_EVALUATION_CONFIG = Path("configs/final/ei_gazebo.yaml")
EXPECTED_BENCHMARK_ID = "moderate_social_navigation_v6"
EXPECTED_REFERENCE_METHOD = "base"
EXPECTED_CONDITIONS = 72


class CalibrationError(RuntimeError):
    """Raised when Base calibration provenance or completeness is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_yaml(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CalibrationError(f"cannot read {label}: {path}") from error
    if not isinstance(payload, dict):
        raise CalibrationError(f"{label} must contain a YAML mapping: {path}")
    return payload


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationError(f"cannot read {label}: {path}") from error
    if not isinstance(payload, dict):
        raise CalibrationError(f"{label} must contain a JSON object: {path}")
    return payload


def _inside_root(project_root: Path, value: Path, *, label: str) -> Path:
    root = project_root.resolve()
    resolved = (value if value.is_absolute() else root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise CalibrationError(f"{label} must be inside the project root: {value}") from error
    return resolved


def _manifest_conditions(document: Mapping[str, Any]) -> set[tuple[str, int]]:
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list):
        raise CalibrationError("validation split must contain a scenarios list")
    conditions: set[tuple[str, int]] = set()
    for index, row in enumerate(scenarios):
        if not isinstance(row, Mapping):
            raise CalibrationError(f"validation scenario {index} must be a mapping")
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            raise CalibrationError(f"validation scenario {index} has no scenario_id")
        try:
            seed = int(row["seed"])
        except (KeyError, TypeError, ValueError) as error:
            raise CalibrationError(f"validation scenario {index} has no integer seed") from error
        condition = (scenario_id, seed)
        if condition in conditions:
            raise CalibrationError(f"duplicate validation condition: {condition!r}")
        conditions.add(condition)
    return conditions


def _atomic_write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_base_calibration(
    *,
    results_path: Path,
    split_manifest_path: Path,
    output_path: Path,
    expected_conditions: int = EXPECTED_CONDITIONS,
    reference_method: str = EXPECTED_REFERENCE_METHOD,
) -> dict[str, Any]:
    """Validate the unfiltered Base table and write the preregistered gate report."""

    if expected_conditions != EXPECTED_CONDITIONS:
        raise CalibrationError(
            f"moderate-v6 calibration is frozen to {EXPECTED_CONDITIONS} conditions"
        )
    if reference_method != EXPECTED_REFERENCE_METHOD:
        raise CalibrationError("moderate-v6 calibration is frozen to the Base reference method")
    try:
        results = pd.read_parquet(results_path)
    except (OSError, ValueError) as error:
        raise CalibrationError(
            f"cannot read collected calibration results: {results_path}"
        ) from error
    try:
        moderate._required_columns(results)
    except ValueError as error:
        raise CalibrationError(str(error)) from error

    methods = set(results["source_policy"].astype(str))
    if methods != {reference_method}:
        raise CalibrationError(
            f"calibration results must be Base-only; observed source policies: {sorted(methods)!r}"
        )
    splits = set(results["split"].astype(str).str.lower())
    if splits != {"validation"}:
        raise CalibrationError(
            "calibration results must contain validation rows only; "
            f"observed splits: {sorted(splits)!r}"
        )
    if len(results) != expected_conditions:
        raise CalibrationError(
            f"calibration requires exactly {expected_conditions} Base rows; got {len(results)}"
        )
    duplicate = results.duplicated(subset=["scenario_id", "seed"], keep=False)
    if bool(duplicate.any()):
        example = results.loc[duplicate, ["scenario_id", "seed"]].iloc[0].to_dict()
        raise CalibrationError(f"duplicate Base validation condition: {example!r}")

    split_document = _load_yaml(split_manifest_path, label="validation split")
    if split_document.get("split") != "validation":
        raise CalibrationError("calibration split must declare split: validation")
    if split_document.get("benchmark_id") != EXPECTED_BENCHMARK_ID:
        raise CalibrationError(
            "calibration split benchmark drift: "
            f"expected {EXPECTED_BENCHMARK_ID!r}, got {split_document.get('benchmark_id')!r}"
        )
    manifest_conditions = _manifest_conditions(split_document)
    if len(manifest_conditions) != expected_conditions:
        raise CalibrationError(
            f"validation split requires {expected_conditions} conditions; "
            f"got {len(manifest_conditions)}"
        )
    result_conditions = {
        (str(row.scenario_id), int(row.seed))
        for row in results.loc[:, ["scenario_id", "seed"]].itertuples(index=False)
    }
    if result_conditions != manifest_conditions:
        raise CalibrationError(
            "Base results do not exactly cover the frozen validation split; "
            f"missing={len(manifest_conditions - result_conditions)}, "
            f"unexpected={len(result_conditions - manifest_conditions)}"
        )

    try:
        valid = moderate._valid_mask(results)
    except ValueError as error:
        raise CalibrationError(str(error)) from error
    if not bool(valid.all()):
        raise CalibrationError(
            "all Base calibration conditions require a retained algorithm outcome before gating"
        )
    report = moderate.build_calibration_report(results, reference_method=reference_method)
    _atomic_write_report(output_path, report)
    return report


def verify_frozen_calibration(
    *,
    project_root: Path,
    report_path: Path,
    evaluation_config_path: Path,
) -> dict[str, Any]:
    """Verify the accepted report path, digest, split, and counts without reading test data."""

    root = project_root.resolve()
    config_path = _inside_root(root, evaluation_config_path, label="evaluation config")
    report_file = _inside_root(root, report_path, label="calibration report")
    config = _load_yaml(config_path, label="evaluation config")
    benchmark = config.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise CalibrationError("evaluation config requires a benchmark mapping")
    if benchmark.get("id") != EXPECTED_BENCHMARK_ID:
        raise CalibrationError("evaluation config is not frozen to moderate-v6")
    if benchmark.get("calibration_policy") != "validation_only_before_test":
        raise CalibrationError("evaluation config calibration policy is not validation-only")
    try:
        configured_report = _inside_root(
            root, Path(str(benchmark["calibration_report"])), label="configured calibration report"
        )
        configured_digest = str(benchmark["calibration_report_sha256"])
        split_path = _inside_root(
            root, Path(str(benchmark["calibration_split"])), label="configured validation split"
        )
        split_digest = str(benchmark["calibration_split_sha256"])
    except KeyError as error:
        raise CalibrationError(
            f"evaluation config is missing frozen calibration field: {error}"
        ) from error
    if configured_report != report_file:
        raise CalibrationError(
            "calibration report path disagrees with the frozen evaluation config"
        )
    if not report_file.is_file():
        raise CalibrationError(f"missing frozen calibration report: {report_file}")
    if _sha256(report_file) != configured_digest:
        raise CalibrationError(
            "calibration report SHA256 disagrees with the frozen evaluation config"
        )
    if not split_path.is_file() or _sha256(split_path) != split_digest:
        raise CalibrationError(
            "validation split SHA256 disagrees with the frozen evaluation config"
        )

    split_document = _load_yaml(split_path, label="validation split")
    if split_document.get("split") != "validation":
        raise CalibrationError("configured calibration split is not validation")
    if split_document.get("benchmark_id") != EXPECTED_BENCHMARK_ID:
        raise CalibrationError("configured calibration split is not moderate-v6")
    condition_count = len(_manifest_conditions(split_document))
    report = _load_json(report_file, label="calibration report")
    counts = report.get("counts")
    if not isinstance(counts, Mapping):
        raise CalibrationError("calibration report requires a counts mapping")
    if (
        report.get("split") != "validation"
        or report.get("reference_method") != EXPECTED_REFERENCE_METHOD
        or report.get("status") != "accepted"
        or report.get("passed") is not True
        or report.get("no_scenario_or_seed_filtering") is not True
    ):
        raise CalibrationError("calibration report is not an accepted unfiltered Base validation")
    if (
        int(counts.get("manifest_episode_count", -1)) != condition_count
        or int(counts.get("valid_episode_count", -1)) != condition_count
    ):
        raise CalibrationError(
            "calibration report does not cover every frozen validation condition"
        )
    if report.get("thresholds") != moderate.CALIBRATION_THRESHOLDS:
        raise CalibrationError("calibration thresholds disagree with the preregistered gate")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=None)
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLIT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--expected-conditions",
        type=int,
        choices=(EXPECTED_CONDITIONS,),
        default=EXPECTED_CONDITIONS,
    )
    parser.add_argument(
        "--reference-method",
        choices=(EXPECTED_REFERENCE_METHOD,),
        default=EXPECTED_REFERENCE_METHOD,
    )
    parser.add_argument("--verify-report", type=Path, default=None)
    parser.add_argument("--evaluation-config", type=Path, default=DEFAULT_EVALUATION_CONFIG)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.verify_report is not None:
            if args.results is not None:
                raise CalibrationError("--verify-report and --results are mutually exclusive")
            report = verify_frozen_calibration(
                project_root=ROOT,
                report_path=args.verify_report,
                evaluation_config_path=args.evaluation_config,
            )
            print(
                "Calibration PASS: accepted Base validation report "
                f"({report['counts']['valid_episode_count']} conditions)"
            )
            return 0
        results_path = args.results or DEFAULT_RESULTS
        report = build_base_calibration(
            results_path=results_path,
            split_manifest_path=args.split_manifest,
            output_path=args.output,
            expected_conditions=args.expected_conditions,
            reference_method=args.reference_method,
        )
        print(
            f"Calibration {str(report['status']).upper()}: "
            f"{report['counts']['valid_episode_count']} complete Base validation conditions"
        )
        return 0 if report["passed"] is True else 1
    except (CalibrationError, KeyError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
