from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "statistics.py"
    spec = importlib.util.spec_from_file_location("final_statistics", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(pair_id: str, policy: str, outcome: str, value: float) -> dict[str, Any]:
    return {
        "episode_id": f"{pair_id}_{policy}_a0_dwb",
        "pair_id": pair_id,
        "scenario_id": pair_id,
        "seed": int(pair_id[-1]),
        "source_policy": policy,
        "outcome": outcome,
        "included_in_algorithm_metrics": outcome not in {"SIMULATOR_FAILURE", "INVALID_RESET"},
        "simulator_failure_attempt_count": int(outcome == "SIMULATOR_FAILURE"),
        "invalid_reset_attempt_count": int(outcome == "INVALID_RESET"),
        "episode_duration_s": value,
        "path_length_m": value,
        "spl": float(outcome == "GOAL_REACHED"),
        "min_human_distance_m": value,
        "personal_space_violation_ratio": value / 100.0,
        "discomfort_time_s": value,
        "emergency_stop_count": value,
        "recovery_trigger_count": value,
        "intervention_ratio": value / 100.0,
        "mean_abs_angular_jerk_rad_s3": value,
    }


def test_paired_statistics_report_exact_tests_holm_and_exclusions() -> None:
    module = _module()
    rows = [
        _record("pair1", "base", "COLLISION", 1.0),
        _record("pair1", "bc", "GOAL_REACHED", 2.0),
        _record("pair2", "base", "GOAL_REACHED", 3.0),
        _record("pair2", "bc", "GOAL_REACHED", 3.0),
        _record("pair3", "base", "TIMEOUT", 4.0),
        _record("pair3", "bc", "GOAL_REACHED", 5.0),
        _record("pair4", "base", "SIMULATOR_FAILURE", 6.0),
        _record("pair4", "bc", "GOAL_REACHED", 6.0),
    ]
    payload = module.build_statistics(pd.DataFrame(rows), bootstrap_samples=100, bootstrap_seed=7)
    assert payload["valid_pair_count"] == 3
    assert payload["excluded_pair_count"] == 1
    assert payload["excluded_episode_counts"]["base"]["simulator_failure"] == 1
    success = payload["binary_outcomes"]["goal_reached"]
    assert success["reference_count"] == 1
    assert success["treatment_count"] == 3
    assert success["mcnemar_exact"]["treatment_only"] == 2
    assert success["mcnemar_exact"]["pvalue_raw"] == 0.5
    assert success["mcnemar_exact"]["pvalue_holm"] >= 0.5
    spl = payload["continuous_metrics"]["spl"]
    assert spl["pair_count"] == 3
    assert "rank_biserial_correlation" in spl["effect_size"]
    duration = payload["continuous_metrics"]["successful_episode_duration_s"]
    assert duration["pair_count"] == 1
    assert duration["wilcoxon"]["pvalue_raw"] == 1.0


def test_all_ties_are_not_reported_as_significant() -> None:
    module = _module()
    rows = [
        _record(pair, policy, "GOAL_REACHED", 2.0)
        for pair in ("pair1", "pair2")
        for policy in ("base", "bc")
    ]
    payload = module.build_statistics(pd.DataFrame(rows), bootstrap_samples=50)
    metric = payload["continuous_metrics"]["spl"]
    assert metric["difference_treatment_minus_reference"]["estimate"] == 0.0
    assert metric["wilcoxon"]["pvalue_raw"] == 1.0
    assert metric["wilcoxon"]["pvalue_holm"] == 1.0
    assert metric["effect_size"]["cohen_dz"] == 0.0
    assert metric["effect_size"]["rank_biserial_correlation"] == 0.0


def test_statistics_cli_writes_strict_json(tmp_path: Path) -> None:
    module = _module()
    results_path = tmp_path / "results.parquet"
    output_path = tmp_path / "statistics.json"
    rows = [
        _record("pair1", "base", "GOAL_REACHED", 2.0),
        _record("pair1", "bc", "GOAL_REACHED", 2.0),
    ]
    pd.DataFrame(rows).to_parquet(results_path, index=False)
    module.main(
        [
            "--results",
            str(results_path),
            "--output",
            str(output_path),
            "--bootstrap-samples",
            "25",
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["bootstrap"]["samples"] == 25
