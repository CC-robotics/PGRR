from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "collect_results.py"
    spec = importlib.util.spec_from_file_location("collect_results", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(
    timestamp: float,
    x: float,
    human_distance: float,
    state: int,
    action: int,
    omega: float,
) -> dict[str, Any]:
    command = [0.2, omega]
    base_command = [0.2, 0.0] if state else command
    return {
        "timestamp": timestamp,
        "robot_pose": [x, 0.0, 0.0],
        "robot_velocity": [0.2, omega],
        "cmd_vel": command,
        "base_cmd_vel": base_command,
        "goal": [3.0, 0.0, 0.0],
        "distance_to_goal": 3.0 - x,
        "failure_score": 0.8 if state in {1, 2, 4} else 0.1,
        "global_path": [[0.0, 0.0], [3.0, 0.0]],
        "nearest_obstacle_distance": 0.8 + x,
        "recovery_state": state,
        "recovery_action": action,
        "privileged": {
            "robot_pose": [x, 0.0, 0.0],
            "nearest_human_distance": human_distance,
        },
    }


def _write_episode(
    raw_dir: Path,
    episode_id: str,
    policy: str,
    outcome: str,
    rows: list[dict[str, Any]],
) -> None:
    prefix = raw_dir / episode_id
    prefix.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "scenario_id": "crossing_flow_high_test_s03220",
                "seed": 3220,
                "source_policy": policy,
                "planner_id": "dwb",
                "project_commit": "frozen",
                "arena_commit": "arena",
                "split": "test",
            }
        ),
        encoding="utf-8",
    )
    prefix.with_suffix(".outcome.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "outcome": outcome,
                "sample_count": len(rows),
                "physical_goal_distance_m": 0.2 if outcome == "GOAL_REACHED" else 1.0,
            }
        ),
        encoding="utf-8",
    )
    prefix.with_suffix(".jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_collection_resolves_retry_and_computes_navigation_metrics(tmp_path: Path) -> None:
    module = _module()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    base_id = "crossing_flow_high_test_s03220_final_base_a0_dwb"
    bc_a0 = "crossing_flow_high_test_s03220_final_bc_a0_dwb"
    bc_a1 = "crossing_flow_high_test_s03220_final_bc_a1_dwb"
    rows = [
        _row(0.0, 0.0, 1.1, 0, 24, 0.0),
        _row(1.0, 1.0, 0.9, 2, 3, 1.0),
        _row(2.0, 2.0, 1.3, 4, 21, 0.0),
        _row(3.0, 3.0, 1.3, 0, 24, 1.0),
    ]
    _write_episode(raw_dir, base_id, "base", "GOAL_REACHED", rows)
    _write_episode(raw_dir, bc_a1, "bc", "COLLISION", rows)
    (raw_dir / bc_a0).with_suffix(".outcome.json").write_text(
        json.dumps(
            {
                "episode_id": bc_a0,
                "outcome": "SIMULATOR_FAILURE",
                "detail": "startup",
            }
        ),
        encoding="utf-8",
    )

    manifest = pd.DataFrame(
        [
            {
                "task_index": 0,
                "episode_id": base_id,
                "pair_id": "pair-1",
                "scenario_id": "crossing_flow_high_test_s03220",
                "seed": 3220,
                "method": "base",
                "shortest_path_length_m": 3.0,
            },
            {
                "task_index": 1,
                "episode_id": bc_a0,
                "pair_id": "pair-1",
                "scenario_id": "crossing_flow_high_test_s03220",
                "seed": 3220,
                "method": "bc",
                "shortest_path_length_m": 3.0,
            },
        ]
    )
    manifest_path = tmp_path / "episode_manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)
    run_manifest = {
        "worker_errors": [],
        "results": [
            {
                "task_index": 0,
                "status": "complete",
                "episode_id": base_id,
                "attempts": [{"attempt": 0, "episode_id": base_id, "outcome": "GOAL_REACHED"}],
            },
            {
                "task_index": 1,
                "status": "complete",
                "episode_id": bc_a1,
                "attempts": [
                    {
                        "attempt": 0,
                        "episode_id": bc_a0,
                        "outcome": "SIMULATOR_FAILURE",
                    },
                    {"attempt": 1, "episode_id": bc_a1, "outcome": "COLLISION"},
                ],
            },
        ],
    }
    (tmp_path / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")

    results = module.collect_results(manifest_path, raw_dir)
    assert list(results["episode_id"]) == [base_id, bc_a1]
    assert list(results["logical_episode_id"]) == [base_id, bc_a0]
    base = results[results["source_policy"] == "base"].iloc[0]
    bc = results[results["source_policy"] == "bc"].iloc[0]
    assert base["path_length_m"] == pytest.approx(3.0)
    assert base["navigation_time_s"] == pytest.approx(base["episode_duration_s"])
    assert base["spl"] == pytest.approx(1.0)
    assert bc["spl"] == 0.0
    assert base["personal_space_violation_ratio"] == pytest.approx(2.0 / 3.0)
    assert base["discomfort_time_s"] == pytest.approx(1.0)
    assert base["emergency_stop_count"] == 1
    assert base["recovery_trigger_count"] == 1
    assert base["recovery_success_count"] == 0
    assert base["recovery_success_rate"] == 0.0
    assert base["intervention_ratio"] == pytest.approx(2.0 / 3.0)
    assert base["mean_abs_angular_jerk_rad_s3"] == pytest.approx(2.0)
    assert base["timeline_recovery_state"] == ["NORMAL", "RECOVERY", "EMERGENCY_STOP", "NORMAL"]
    assert bc["physical_attempt_count"] == 2
    assert bc["simulator_failure_attempt_count"] == 1
    assert bc["excluded_attempt_count"] == 1

    summary = module.build_summary(results).set_index("source_policy")
    assert summary.loc["bc", "simulator_failure_count"] == 1
    assert summary.loc["bc", "excluded_attempt_count"] == 1
    assert summary.loc["bc", "algorithm_episode_count"] == 1

    results_path = tmp_path / "results.parquet"
    summary_path = tmp_path / "summary.csv"
    statistics_path = tmp_path / "statistics.json"
    module.write_outputs(
        manifest_path=manifest_path,
        raw_dir=raw_dir,
        run_manifest_path=tmp_path / "run_manifest.json",
        results_path=results_path,
        summary_path=summary_path,
        statistics_path=statistics_path,
        reference_policy="base",
        treatment_policy="bc",
        bootstrap_samples=25,
        bootstrap_seed=4,
    )
    assert len(pd.read_parquet(results_path)) == 2
    final_summary = pd.read_csv(summary_path)
    assert len(final_summary[final_summary["row_type"] == "method_summary"]) == 2
    assert len(final_summary[final_summary["row_type"] == "statistic"]) >= 3
    statistic_metrics = set(final_summary.loc[final_summary["row_type"] == "statistic", "metric"])
    assert "goal_reached" in statistic_metrics
    assert "min_human_distance_m" in statistic_metrics
    statistics = json.loads(statistics_path.read_text(encoding="utf-8"))
    assert statistics["valid_pair_count"] == 1
    assert statistics["excluded_episode_counts"]["bc"]["simulator_failure"] == 1

    collection_dir = tmp_path / "collection_only"
    collection_results = collection_dir / "results.parquet"
    collection_summary = collection_dir / "collector_summary.csv"
    module.main(
        [
            "--manifest",
            str(manifest_path),
            "--run-manifest",
            str(tmp_path / "run_manifest.json"),
            "--raw-dir",
            str(raw_dir),
            "--results",
            str(collection_results),
            "--summary",
            str(collection_summary),
            "--collection-only",
        ]
    )
    collected = pd.read_parquet(collection_results)
    method_summary = pd.read_csv(collection_summary)
    assert len(collected) == 2
    assert set(method_summary["row_type"]) == {"method_summary"}
    assert int(method_summary["simulator_failure_count"].sum()) == 1
    assert int(method_summary["excluded_attempt_count"].sum()) == 1
    assert not (collection_dir / "statistics.json").exists()

    with pytest.raises(ValueError, match=r"must differ.*collection-only"):
        module.write_outputs(
            manifest_path=manifest_path,
            raw_dir=raw_dir,
            run_manifest_path=tmp_path / "run_manifest.json",
            results_path=tmp_path / "unsafe_results.parquet",
            summary_path=tmp_path / "unsafe_summary.csv",
            statistics_path=tmp_path / "unsafe_statistics.json",
            reference_policy="base",
            treatment_policy="base",
            bootstrap_samples=25,
            bootstrap_seed=4,
        )
    assert not (tmp_path / "unsafe_statistics.json").exists()


def test_collection_refuses_missing_algorithm_artifact(tmp_path: Path) -> None:
    module = _module()
    manifest_path = tmp_path / "manifest.parquet"
    pd.DataFrame([{"episode_id": "missing", "method": "base"}]).to_parquet(
        manifest_path, index=False
    )
    with pytest.raises(FileNotFoundError, match="missing required artifacts"):
        module.collect_results(manifest_path, tmp_path)


def test_recovery_success_rate_uses_completed_sequences_per_trigger() -> None:
    module = _module()
    rows = [
        _row(0.0, 0.0, 2.0, 0, 24, 0.0),
        _row(1.0, 1.0, 2.0, 2, 3, 0.2),
        _row(2.0, 2.0, 2.0, 3, 24, 0.0),
        _row(3.0, 3.0, 2.0, 0, 24, 0.0),
    ]
    metrics = module._control_metrics(rows, pd.Series([0.0, 1.0, 2.0, 3.0]).to_numpy())
    assert metrics["recovery_trigger_count"] == 1
    assert metrics["recovery_success_count"] == 1
    assert metrics["recovery_success_rate"] == 1.0


def test_terminal_navigation_success_is_not_a_recovery_success() -> None:
    module = _module()
    rows = [
        _row(0.0, 0.0, 2.0, 0, 24, 0.0),
        _row(1.0, 1.0, 2.0, 2, 3, 0.2),
        _row(2.0, 2.0, 2.0, 6, 24, 0.0),
    ]
    metrics = module._control_metrics(rows, pd.Series([0.0, 1.0, 2.0]).to_numpy())
    assert metrics["recovery_trigger_count"] == 1
    assert metrics["recovery_success_count"] == 0
    assert metrics["recovery_success_rate"] == 0.0


def test_excluded_terminal_episode_may_have_an_empty_stream(tmp_path: Path) -> None:
    module = _module()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    episode_id = "invalid"
    prefix = raw_dir / episode_id
    prefix.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "scenario_id": "scenario",
                "seed": 1,
                "source_policy": "base",
                "project_commit": "frozen",
            }
        ),
        encoding="utf-8",
    )
    prefix.with_suffix(".outcome.json").write_text(
        json.dumps({"episode_id": episode_id, "outcome": "INVALID_RESET"}),
        encoding="utf-8",
    )
    prefix.with_suffix(".jsonl").write_text("", encoding="utf-8")
    manifest_path = tmp_path / "manifest.parquet"
    pd.DataFrame([{"episode_id": episode_id, "method": "base"}]).to_parquet(
        manifest_path, index=False
    )
    results = module.collect_results(manifest_path, raw_dir)
    assert not bool(results.iloc[0]["included_in_algorithm_metrics"])
    assert results.iloc[0]["exclusion_reason"] == "INVALID_RESET"
    summary = module.build_summary(results).iloc[0]
    assert summary["invalid_reset_count"] == 1
    assert summary["excluded_attempt_count"] == 1
