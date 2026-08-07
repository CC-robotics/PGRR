from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate/calibrate_moderate.py"
SPEC = importlib.util.spec_from_file_location("pgrr_calibrate_moderate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validation_document() -> dict[str, Any]:
    payload = yaml.safe_load(
        (ROOT / "scenarios/splits/moderate_v6_validation.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    return payload


def _base_results() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, scenario in enumerate(_validation_document()["scenarios"]):
        outcome = "GOAL_REACHED" if index < 53 else "COLLISION"
        scenario_id = str(scenario["scenario_id"])
        seed = int(scenario["seed"])
        rows.append(
            {
                "episode_id": f"{scenario_id}_eval_base_a0_dwb",
                "pair_id": f"{scenario_id}_pair",
                "scenario_id": scenario_id,
                "family": scenario["family"],
                "density": scenario["density"],
                "seed": seed,
                "split": "validation",
                "source_policy": "base",
                "outcome": outcome,
                "included_in_algorithm_metrics": True,
                "min_human_distance_m": 1.5,
                "project_commit": "a" * 40,
            }
        )
    return pd.DataFrame(rows)


def _write_split(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(_validation_document(), sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_base_only_cli_builds_the_unfiltered_accepted_report(tmp_path: Path) -> None:
    results_path = tmp_path / "results.parquet"
    split_path = _write_split(tmp_path / "validation.yaml")
    output_path = tmp_path / "calibration_report.json"
    _base_results().to_parquet(results_path, index=False)

    report = MODULE.build_base_calibration(
        results_path=results_path,
        split_manifest_path=split_path,
        output_path=output_path,
    )

    assert report["status"] == "accepted"
    assert report["passed"] is True
    assert report["reference_method"] == "base"
    assert report["split"] == "validation"
    assert report["no_scenario_or_seed_filtering"] is True
    assert report["counts"]["manifest_episode_count"] == 72
    assert report["counts"]["valid_episode_count"] == 72
    assert report["metrics"]["success_rate"] == pytest.approx(53 / 72)
    assert report["metrics"]["collision_plus_timeout_rate"] == pytest.approx(19 / 72)
    assert json.loads(output_path.read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("mutation", ["missing", "second_method", "test_split", "excluded"])
def test_base_calibration_rejects_partial_or_non_base_inputs(
    tmp_path: Path,
    mutation: str,
) -> None:
    results = _base_results()
    if mutation == "missing":
        results = results.iloc[:-1].copy()
    elif mutation == "second_method":
        results.loc[0, "source_policy"] = "pgrr"
    elif mutation == "test_split":
        results.loc[0, "split"] = "test"
    else:
        results.loc[0, "outcome"] = "SIMULATOR_FAILURE"
        results.loc[0, "included_in_algorithm_metrics"] = False
    results_path = tmp_path / "results.parquet"
    results.to_parquet(results_path, index=False)

    with pytest.raises(MODULE.CalibrationError):
        MODULE.build_base_calibration(
            results_path=results_path,
            split_manifest_path=_write_split(tmp_path / "validation.yaml"),
            output_path=tmp_path / "report.json",
        )


def test_calibration_contract_cannot_be_retargeted(tmp_path: Path) -> None:
    results_path = tmp_path / "results.parquet"
    _base_results().to_parquet(results_path, index=False)
    split_path = _write_split(tmp_path / "validation.yaml")

    with pytest.raises(MODULE.CalibrationError, match="72 conditions"):
        MODULE.build_base_calibration(
            results_path=results_path,
            split_manifest_path=split_path,
            output_path=tmp_path / "report.json",
            expected_conditions=71,
        )
    with pytest.raises(MODULE.CalibrationError, match="Base reference"):
        MODULE.build_base_calibration(
            results_path=results_path,
            split_manifest_path=split_path,
            output_path=tmp_path / "report.json",
            reference_method="pgrr",
        )


def test_verify_mode_locks_report_hash_without_opening_a_test_manifest(tmp_path: Path) -> None:
    split_path = _write_split(tmp_path / "scenarios/splits/moderate_v6_validation.yaml")
    results_path = tmp_path / "results.parquet"
    report_path = tmp_path / "outputs/calibration_report.json"
    _base_results().to_parquet(results_path, index=False)
    MODULE.build_base_calibration(
        results_path=results_path,
        split_manifest_path=split_path,
        output_path=report_path,
    )
    config_path = tmp_path / "configs/final/ei_gazebo.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "benchmark": {
                    "id": "moderate_social_navigation_v6",
                    "calibration_policy": "validation_only_before_test",
                    "calibration_split": split_path.relative_to(tmp_path).as_posix(),
                    "calibration_split_sha256": _sha256(split_path),
                    "calibration_report": report_path.relative_to(tmp_path).as_posix(),
                    "calibration_report_sha256": _sha256(report_path),
                },
                # The nonexistent path proves verification never opens held-out data.
                "runtime": {"split": "test", "split_manifest": "/definitely/not/read.yaml"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report = MODULE.verify_frozen_calibration(
        project_root=tmp_path,
        report_path=report_path.relative_to(tmp_path),
        evaluation_config_path=config_path.relative_to(tmp_path),
    )
    assert report["passed"] is True

    report_path.write_bytes(report_path.read_bytes() + b" ")
    with pytest.raises(MODULE.CalibrationError, match="SHA256"):
        MODULE.verify_frozen_calibration(
            project_root=tmp_path,
            report_path=report_path.relative_to(tmp_path),
            evaluation_config_path=config_path.relative_to(tmp_path),
        )
