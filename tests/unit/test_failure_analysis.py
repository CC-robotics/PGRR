from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "failure_analysis.py"
    spec = importlib.util.spec_from_file_location("failure_analysis", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(
    episode_id: str,
    outcome: str,
    detail: str,
    *,
    method: str = "bc",
    distances: list[float] | None = None,
) -> dict[str, Any]:
    times = [0.0, 2.0, 4.0, 6.0]
    return {
        "episode_id": episode_id,
        "source_policy": method,
        "family": "doorway_bottleneck",
        "density": "high",
        "outcome": outcome,
        "outcome_detail": detail,
        "included_in_algorithm_metrics": outcome not in {"SIMULATOR_FAILURE", "INVALID_RESET"},
        "project_commit": "frozen-commit",
        "raw_sha256": "0" * 64,
        "timeline_time_s": times,
        "timeline_distance_to_goal_m": distances or [3.0, 2.8, 2.75, 2.74],
        "timeline_recovery_state": ["NORMAL", "RECOVERY", "REJOIN", "NORMAL"],
        "recovery_trigger_count": 1,
        "recovery_action_sample_count": 3,
        "intervention_ratio": 0.25,
        "excluded_attempt_count": 0,
    }


def test_classification_requires_explicit_collision_type_and_detects_stagnation() -> None:
    module = _module()
    human = _record("human", "COLLISION", "privileged robot-human overlap")
    static = _record(
        "static", "COLLISION", "physical footprint intersects known static scenario geometry"
    )
    ambiguous = _record(
        "ambiguous", "COLLISION", "LiDAR obstacle return lies inside the robot footprint"
    )
    timeout = _record("timeout", "TIMEOUT", "configured episode timeout")

    assert (
        module.classify_episode(human, terminal_window_s=4.0, stagnation_threshold_m=0.15)[0]
        == "collision_human"
    )
    assert (
        module.classify_episode(static, terminal_window_s=4.0, stagnation_threshold_m=0.15)[0]
        == "collision_static"
    )
    assert (
        module.classify_episode(ambiguous, terminal_window_s=4.0, stagnation_threshold_m=0.15)[0]
        == "collision_unattributed"
    )
    category, _, progress = module.classify_episode(
        timeout, terminal_window_s=4.0, stagnation_threshold_m=0.15
    )
    assert category == "timeout_stagnation"
    assert progress == pytest.approx(0.06)


def test_report_uses_only_final_table_and_sha_verifies_representatives(tmp_path: Path) -> None:
    module = _module()
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    records = [
        _record("base_collision", "COLLISION", "privileged robot-human overlap", method="base"),
        _record("bc_timeout", "TIMEOUT", "configured episode timeout"),
        _record("bc_abort", "PLANNER_FAILURE", "local planner aborted"),
        _record("bc_success", "GOAL_REACHED", "goal reached"),
    ]
    for record in records:
        raw_path = raw_dir / f"{record['episode_id']}.jsonl"
        raw_path.write_text('{"recorded": true}\n', encoding="utf-8")
        record["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    results_path = tmp_path / "outputs" / "final" / "results.parquet"
    results_path.parent.mkdir(parents=True)
    original = pd.DataFrame(records)
    original.to_parquet(results_path, index=False)
    before = results_path.read_bytes()

    output_path = results_path.with_name("failure_analysis.md")
    assert (
        module.main(
            [
                "--results",
                str(results_path),
                "--output",
                str(output_path),
                "--raw-dir",
                str(raw_dir),
            ]
        )
        == 0
    )
    report = output_path.read_text(encoding="utf-8")
    assert "Human collision | 1" in report
    assert "Timeout / terminal stagnation | 1" in report
    assert "Planner abort | 1" in report
    assert "base_collision.jsonl" in report
    assert records[0]["raw_sha256"] in report
    assert "WAIT samples" in report and "not recorded" in report
    assert "does not by itself establish" in report
    assert results_path.read_bytes() == before


def test_missing_final_results_fails_without_pilot_fallback(tmp_path: Path) -> None:
    module = _module()
    pilot = tmp_path / "outputs" / "pilot" / "results.parquet"
    pilot.parent.mkdir(parents=True)
    pd.DataFrame([{"irrelevant": True}]).to_parquet(pilot, index=False)
    with pytest.raises(FileNotFoundError, match="no pilot fallback"):
        module.main(
            [
                "--results",
                str(tmp_path / "outputs" / "final" / "results.parquet"),
                "--output",
                str(tmp_path / "outputs" / "final" / "failure_analysis.md"),
            ]
        )


def test_report_rejects_raw_sha_mismatch(tmp_path: Path) -> None:
    module = _module()
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    record = _record("collision", "COLLISION", "privileged robot-human overlap")
    (raw_dir / "collision.jsonl").write_text("changed\n", encoding="utf-8")
    results_path = tmp_path / "results.parquet"
    pd.DataFrame([record]).to_parquet(results_path, index=False)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        module.build_report(
            pd.read_parquet(results_path),
            results_path=results_path,
            raw_dir=raw_dir,
            root=tmp_path,
        )
