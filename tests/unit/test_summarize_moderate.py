from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "summarize_moderate.py"
    spec = importlib.util.spec_from_file_location("summarize_moderate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


METHODS = ("base", "standard", "heuristic", "pgrr")
FAMILIES = tuple(f"family_{index}" for index in range(6))
DENSITIES = ("low", "medium", "high")


def _outcomes(method: str) -> list[str]:
    if method == "base":
        return ["GOAL_REACHED"] * 18 + ["COLLISION"] * 6 + ["TIMEOUT"] * 6
    if method == "standard":
        return ["GOAL_REACHED"] * 20 + ["COLLISION"] * 5 + ["TIMEOUT"] * 5
    if method == "heuristic":
        return ["GOAL_REACHED"] * 21 + ["COLLISION"] * 3 + ["TIMEOUT"] * 6
    return ["GOAL_REACHED"] * 27 + ["COLLISION"] + ["TIMEOUT"] * 2


def _results() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    conditions = [
        (family, replicate, DENSITIES[replicate % len(DENSITIES)])
        for family in FAMILIES
        for replicate in range(5)
    ]
    for method_index, method in enumerate(METHODS):
        outcomes = _outcomes(method)
        for index, ((family, replicate, density), outcome) in enumerate(
            zip(conditions, outcomes, strict=True)
        ):
            seed = 200_000 + index
            pair_id = f"{family}_{density}_validation_s{seed}_r{replicate}"
            # Four of five episodes in every family satisfy the observable
            # interaction criterion, so Base's ratio is exactly 0.8 and all
            # six families are represented.
            human_distance = 1.4 if replicate < 4 else 2.4
            value = float(index + method_index + 1)
            rows.append(
                {
                    "episode_id": f"{pair_id}_{method}",
                    "pair_id": pair_id,
                    "scenario_id": pair_id,
                    "family": family,
                    "density": density,
                    "seed": seed,
                    "split": "validation",
                    "source_policy": method,
                    "method": method,
                    "outcome": outcome,
                    "included_in_algorithm_metrics": True,
                    "project_commit": "frozen",
                    "episode_duration_s": value + 10.0,
                    "navigation_time_s": value + 10.0,
                    "path_length_m": value,
                    "spl": float(outcome == "GOAL_REACHED") * (0.7 + 0.01 * method_index),
                    "min_human_distance_m": human_distance + 0.01 * method_index,
                    "personal_space_violation_ratio": 0.1 + 0.01 * method_index,
                    "discomfort_time_s": 2.0 + method_index,
                    "emergency_stop_count": float(method_index),
                    "recovery_trigger_count": float(method_index),
                    "recovery_success_rate": 0.5 + 0.1 * method_index,
                    "recovery_duration_s": 1.0 + method_index,
                    "intervention_ratio": 0.05 * method_index,
                    "mean_abs_angular_jerk_rad_s3": 0.2 + 0.01 * method_index,
                }
            )
    return pd.DataFrame(rows)


def test_summary_gate_and_global_pairwise_statistics_use_every_condition() -> None:
    module = _module()
    results = _results()
    statistics_module = module._statistics_module()
    evidence = module.validate_complete_condition_sets(
        results,
        methods=METHODS,
        main_method="pgrr",
        statistics=statistics_module,
    )
    assert evidence["condition_count"] == 30
    assert evidence["manifest_episode_count"] == 120

    summary = module.build_summary(results, methods=METHODS)
    base_rows = summary[summary["method"] == "base"]
    assert int(base_rows["outcome_count"].sum()) == 30
    assert len(base_rows) == len(FAMILIES) * len(DENSITIES) * len(module.KNOWN_OUTCOMES)

    calibration = module.build_calibration_report(results)
    assert calibration["passed"] is True
    assert calibration["status"] == "accepted"
    assert calibration["metrics"]["success_rate"] == pytest.approx(0.6)
    assert calibration["metrics"]["collision_plus_timeout_rate"] == pytest.approx(0.4)
    assert calibration["metrics"]["interaction_episode_ratio"] == pytest.approx(0.8)
    assert calibration["counts"]["interaction_family_count"] == 6
    assert calibration["no_scenario_or_seed_filtering"] is True

    statistics = module.build_pairwise_statistics(
        results,
        methods=METHODS,
        bootstrap_samples=40,
        bootstrap_seed=9,
        statistics=statistics_module,
    )
    assert statistics["comparators"] == ["base", "standard", "heuristic"]
    assert statistics["analysis_policy"]["condition_count"] == 30
    assert statistics["analysis_policy"]["scenario_or_seed_filtering"] is False
    assert set(statistics["comparisons"]) == {"base", "standard", "heuristic"}
    assert all(
        comparison["valid_pair_count"] == 30 for comparison in statistics["comparisons"].values()
    )
    global_tests = statistics["global_multiple_comparison"]["hypotheses"]
    assert statistics["global_multiple_comparison"]["hypothesis_count"] == len(global_tests)
    assert len(global_tests) >= 9
    assert all(row["pvalue_holm_global"] >= row["pvalue_raw"] for row in global_tests)
    success = statistics["comparisons"]["base"]["binary_outcomes"]["goal_reached"]
    assert success["reference_count"] == 18
    assert success["treatment_count"] == 27
    assert "pvalue_holm_within_comparison" in success["mcnemar_exact"]


def test_calibration_rejects_out_of_range_base_without_dropping_rows() -> None:
    module = _module()
    results = _results()
    base_indices = results.index[results["source_policy"] == "base"]
    results.loc[base_indices[:24], "outcome"] = "GOAL_REACHED"
    results.loc[base_indices[24:27], "outcome"] = "COLLISION"
    results.loc[base_indices[27:], "outcome"] = "TIMEOUT"
    report = module.build_calibration_report(results)
    assert report["passed"] is False
    assert report["status"] == "rejected"
    assert report["counts"]["valid_episode_count"] == 30
    assert report["metrics"]["success_rate"] == pytest.approx(0.8)
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["success_rate"]["passed"] is False
    assert checks["collision_plus_timeout_rate"]["passed"] is True


def test_pairwise_analysis_rejects_method_specific_condition_subset() -> None:
    module = _module()
    results = _results()
    dropped = results.index[results["source_policy"] == "standard"][0]
    incomplete = results.drop(index=dropped)
    with pytest.raises(ValueError, match="identical preregistered condition sets"):
        module.build_pairwise_statistics(
            incomplete,
            methods=METHODS,
            bootstrap_samples=20,
        )


def test_cli_writes_fixed_artifacts_and_has_no_seed_filter(tmp_path: Path) -> None:
    module = _module()
    results_path = tmp_path / "results.parquet"
    output_dir = tmp_path / "analysis"
    _results().to_parquet(results_path, index=False)
    module.main(
        [
            "--results",
            str(results_path),
            "--output-dir",
            str(output_dir),
            "--methods",
            *METHODS,
            "--bootstrap-samples",
            "25",
            "--bootstrap-seed",
            "3",
        ]
    )
    assert {path.name for path in output_dir.iterdir()} == {
        "summary.csv",
        "pairwise_statistics.json",
        "calibration_report.json",
    }
    summary = pd.read_csv(output_dir / "summary.csv")
    assert int(summary["outcome_count"].sum()) == len(_results())
    statistics = json.loads((output_dir / "pairwise_statistics.json").read_text())
    calibration = json.loads((output_dir / "calibration_report.json").read_text())
    assert statistics["main_method"] == "pgrr"
    assert calibration["condition_sha256"]
    with pytest.raises(SystemExit):
        module.parse_args(["--results", str(results_path), "--seed", "200001"])
