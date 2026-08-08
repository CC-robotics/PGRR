from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REPORT = _load("pgrr_report_assets_test", "scripts/report/build_report_assets.py")
DECK = _load("pgrr_deck_test", "scripts/presentation/build_deck.py")
EVIDENCE = _load("pgrr_matched_evidence_test", "scripts/report/build_matched_run_evidence.py")
SUMMARIZE = _load("pgrr_report_statistics_fixture", "scripts/evaluate/summarize_moderate.py")


def _synthetic_report_results() -> pd.DataFrame:
    outcomes = {
        "base": ["GOAL_REACHED"] * 42
        + ["COLLISION"] * 15
        + ["TIMEOUT"] * 12
        + ["PLANNER_FAILURE"] * 3,
        "standard": ["GOAL_REACHED"] * 45
        + ["COLLISION"] * 12
        + ["TIMEOUT"] * 12
        + ["PLANNER_FAILURE"] * 3,
        "heuristic": ["GOAL_REACHED"] * 48
        + ["COLLISION"] * 9
        + ["TIMEOUT"] * 12
        + ["PLANNER_FAILURE"] * 3,
        "bc_uniform": ["GOAL_REACHED"] * 51
        + ["COLLISION"] * 9
        + ["TIMEOUT"] * 9
        + ["PLANNER_FAILURE"] * 3,
        "pgrr": ["GOAL_REACHED"] * 57
        + ["COLLISION"] * 6
        + ["TIMEOUT"] * 6
        + ["PLANNER_FAILURE"] * 3,
    }
    conditions = [
        (family, density, repeat)
        for family in REPORT.FAMILIES
        for density in REPORT.DENSITIES
        for repeat in range(3)
    ]
    rows: list[dict[str, object]] = []
    for method_index, method in enumerate(REPORT.METHODS):
        for condition_index, ((family, density, repeat), outcome) in enumerate(
            zip(conditions, outcomes[method], strict=True)
        ):
            pair_id = f"fixture_{family}_{density}_r{repeat}"
            scenario_id = f"fixture_{family}_{density}_validation_moderate_v6_r{repeat:02d}"
            pair_id = f"{scenario_id}_seed{810_000 + condition_index}"
            episode_id = f"{scenario_id}_eval_{method}_fixture_a0_dwb"
            rows.append(
                {
                    "episode_id": episode_id,
                    "pair_id": pair_id,
                    "scenario_id": scenario_id,
                    "family": family,
                    "density": density,
                    "replicate": repeat,
                    "seed": 810_000 + condition_index,
                    "split": "validation",
                    "source_policy": method,
                    "outcome": outcome,
                    "included_in_algorithm_metrics": True,
                    "episode_duration_s": 40.0 + condition_index,
                    "navigation_time_s": 39.0 + condition_index + method_index,
                    "path_length_m": 8.0 + 0.1 * condition_index + 0.1 * method_index,
                    "min_human_distance_m": 0.55 + 0.04 * method_index,
                    "recovery_trigger_count": 0 if method == "base" else 4,
                    "recovery_success_count": 0 if method == "base" else method_index,
                    "recovery_duration_s": 0.5 * method_index,
                    "intervention_ratio": 0.02 * method_index,
                    "raw_sha256": "0" * 64,
                    "scenario_sha256": "1" * 64,
                }
            )
    return pd.DataFrame(rows)


def _write_synthetic_report_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    directory = tmp_path / "outputs/report_inputs/validation"
    directory.mkdir(parents=True)
    results = _synthetic_report_results()
    results_path = directory / "results.parquet"
    statistics_path = directory / "pairwise_statistics.json"
    evidence_path = directory / "matched_base_pgrr_evidence.json"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    selected = results.loc[
        (results["family"] == "doorway_bottleneck")
        & (results["density"] == "medium")
        & (results["replicate"] == 0)
        & results["source_policy"].isin(("base", "pgrr"))
    ]
    for row_index, row in selected.iterrows():
        raw_path = raw_dir / f"{row['episode_id']}.jsonl"
        records = [
            {
                "timestamp": float(index),
                "robot_pose": [7.0 + index, 12.0 + 0.1 * index, 0.0],
                "distance_to_goal": 17.0 - index,
                "failure_score": 0.2 * index,
                "recovery_state": 0 if row["source_policy"] == "base" else index % 3,
                "recovery_action": 24 if row["source_policy"] == "base" else 20 + index,
            }
            for index in range(4)
        ]
        raw_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        results.loc[row_index, "raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    results.to_parquet(results_path, index=False)
    statistics = SUMMARIZE.build_pairwise_statistics(
        results,
        methods=REPORT.METHODS,
        main_method="pgrr",
        reference_method="base",
        bootstrap_samples=80,
        bootstrap_seed=97,
    )
    statistics_path.write_text(
        json.dumps(statistics, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    EVIDENCE.build_evidence(
        stage="validation",
        results_path=results_path,
        raw_dir=raw_dir,
        output_path=evidence_path,
    )
    return results_path, statistics_path, evidence_path


def _synthetic_locked_test_media(tmp_path: Path) -> tuple[pd.DataFrame, Path, dict[str, object]]:
    directory = tmp_path / "outputs/moderate/final"
    media = directory / "media"
    media.mkdir(parents=True)
    trajectory = media / REPORT.MATCHED_TRAJECTORY_FILENAME
    timeline = media / REPORT.MATCHED_TIMELINE_FILENAME
    trajectory.write_bytes(b"%PDF-1.4\nsynthetic trajectory\n%%EOF\n")
    timeline.write_bytes(b"%PDF-1.4\nsynthetic recovery timeline\n%%EOF\n")
    pair_id = "fixture_doorway_bottleneck_high_test_moderate_v6_r00_seed91"
    scenario_id = "doorway_bottleneck_high_test_moderate_v6_r00_s91"
    project_commit = "a" * 40
    rows: list[dict[str, object]] = []
    for method, outcome, digest in (
        ("base", "COLLISION", "b"),
        ("pgrr", "GOAL_REACHED", "c"),
    ):
        rows.append(
            {
                "episode_id": f"{scenario_id}_{method}",
                "pair_id": pair_id,
                "scenario_id": scenario_id,
                "scenario_sha256": "1" * 64,
                "family": "doorway_bottleneck",
                "density": "high",
                "seed": 91,
                "source_policy": method,
                "outcome": outcome,
                "included_in_algorithm_metrics": True,
                "project_commit": project_commit,
                "raw_sha256": digest * 64,
                "metadata_sha256": "d" * 64,
                "outcome_sha256": "e" * 64,
                "sample_count": 3,
            }
        )
    results = pd.DataFrame(rows)
    payload: dict[str, object] = {
        "schema_version": 2,
        "artifact_type": "matched_base_pgrr_test_media",
        "benchmark_id": REPORT.BENCHMARK_ID,
        "stage": "test",
        "representation": "telemetry reconstruction; not a simulator camera screenshot",
        "selection_rule": REPORT.MATCHED_TEST_SELECTION_RULE,
        "pair_id": pair_id,
        "scenario_id": scenario_id,
        "scenario_sha256": "1" * 64,
        "family": "doorway_bottleneck",
        "density": "high",
        "seed": 91,
        "project_commit": project_commit,
        "results_file": "results.parquet",
        "results_sha256": "f" * 64,
        "runs": {
            method: {
                "episode_id": row["episode_id"],
                "outcome": row["outcome"],
                "raw_file": f"{row['episode_id']}.jsonl",
                "raw_sha256": row["raw_sha256"],
                "metadata_sha256": row["metadata_sha256"],
                "outcome_sha256": row["outcome_sha256"],
                "sample_count": row["sample_count"],
            }
            for method, row in ((str(row["source_policy"]), row) for row in rows)
        },
        "artifacts": {
            "trajectory": {
                "path": f"media/{trajectory.name}",
                "filename": trajectory.name,
                "sha256": hashlib.sha256(trajectory.read_bytes()).hexdigest(),
                "media_type": "application/pdf",
            },
            "recovery_timeline": {
                "path": f"media/{timeline.name}",
                "filename": timeline.name,
                "sha256": hashlib.sha256(timeline.read_bytes()).hexdigest(),
                "media_type": "application/pdf",
            },
        },
    }
    evidence = directory / REPORT.MATCHED_EVIDENCE_FILENAME
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return results, evidence, payload


def test_pending_report_assets_never_read_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_read(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("pending mode attempted to read a result")

    monkeypatch.setattr(pd, "read_parquet", forbidden_read)
    output = tmp_path / "generated"
    data = REPORT.build_report_assets(
        stage="pending",
        results_path=None,
        output_dir=output,
        project_root=tmp_path,
    )

    assert data["results_available"] is False
    assert json.loads((output / "report_data.json").read_text())["stage"] == "pending"
    macros = (output / "report_stage.tex").read_text()
    assert "ReportResultsAvailablefalse" in macros
    assert "结果尚未锁定" in macros
    assert not list(output.glob("result_*.pdf"))


def test_report_result_path_policy_rejects_live_and_historical_outputs(tmp_path: Path) -> None:
    allowed_test = tmp_path / "outputs/moderate/final/results.parquet"
    allowed_test.parent.mkdir(parents=True)
    allowed_test.write_bytes(b"complete")
    assert (
        REPORT.validate_result_path(allowed_test, stage="test", project_root=tmp_path)
        == allowed_test.resolve()
    )
    allowed_test_statistics = allowed_test.with_name("pairwise_statistics.json")
    allowed_test_statistics.write_bytes(b"complete")
    assert (
        REPORT.validate_statistics_path(
            allowed_test_statistics, stage="test", project_root=tmp_path
        )
        == allowed_test_statistics.resolve()
    )
    allowed_test_evidence = allowed_test.with_name("matched_base_pgrr_evidence.json")
    allowed_test_evidence.write_bytes(b"complete")
    assert (
        REPORT.validate_matched_evidence_path(
            allowed_test_evidence, stage="test", project_root=tmp_path
        )
        == allowed_test_evidence.resolve()
    )

    allowed_validation = tmp_path / "outputs/report_inputs/validation/results.parquet"
    allowed_validation.parent.mkdir(parents=True)
    allowed_validation.write_bytes(b"complete")
    assert (
        REPORT.validate_result_path(allowed_validation, stage="validation", project_root=tmp_path)
        == allowed_validation.resolve()
    )

    forbidden = (
        tmp_path / "outputs/final/results.parquet",
        tmp_path / "outputs/pilot/results.parquet",
        tmp_path / "outputs/moderate/v5_validation/results.parquet",
        tmp_path / "outputs/moderate/v5_validation_comparators/results.parquet",
        tmp_path / "outputs/moderate/v6_validation/results.parquet",
        tmp_path / "outputs/moderate/v6_validation_base_d5fa66b/results.parquet",
        tmp_path / "outputs/moderate/calibration/results.parquet",
        tmp_path / "outputs/report_inputs/validation/old64/results.parquet",
    )
    for path in forbidden:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"forbidden")
        with pytest.raises(REPORT.ReportInputError):
            REPORT.validate_result_path(path, stage="test", project_root=tmp_path)
        statistics = path.with_name("pairwise_statistics.json")
        statistics.write_bytes(b"forbidden")
        with pytest.raises(REPORT.ReportInputError):
            REPORT.validate_statistics_path(statistics, stage="validation", project_root=tmp_path)


def test_locked_test_matched_media_requires_both_fixed_sha_bound_pdfs(tmp_path: Path) -> None:
    results, evidence, payload = _synthetic_locked_test_media(tmp_path)
    summary = REPORT.validate_matched_evidence(
        payload,
        results=results,
        results_sha256="f" * 64,
        stage="test",
        evidence_path=evidence,
    )
    assert summary["artifact_type"] == "matched_base_pgrr_test_media"
    assert set(summary["artifacts"]) == {"trajectory", "recovery_timeline"}
    assert summary["runs"]["base"]["episode_id"] != summary["runs"]["pgrr"]["episode_id"]
    output = tmp_path / "report/generated"
    output.mkdir(parents=True)
    REPORT._copy_fixed_test_media(summary, evidence_path=evidence, output_dir=output)
    assert (output / "result_matched_trajectory.pdf").read_bytes().startswith(b"%PDF")
    assert (output / "result_matched_recovery_timeline.pdf").read_bytes().startswith(b"%PDF")

    escaped = json.loads(json.dumps(payload))
    escaped["artifacts"]["trajectory"]["path"] = f"../{REPORT.MATCHED_TRAJECTORY_FILENAME}"
    with pytest.raises(REPORT.ReportInputError, match="escapes the approved directory"):
        REPORT.validate_matched_evidence(
            escaped,
            results=results,
            results_sha256="f" * 64,
            stage="test",
            evidence_path=evidence,
        )

    timeline = evidence.parent / str(summary["artifacts"]["recovery_timeline"]["path"])
    timeline.write_bytes(b"%PDF-1.4\ntampered\n%%EOF\n")
    with pytest.raises(REPORT.ReportInputError, match="recovery_timeline SHA256 disagrees"):
        REPORT.validate_matched_evidence(
            payload,
            results=results,
            results_sha256="f" * 64,
            stage="test",
            evidence_path=evidence,
        )


def test_locked_test_report_requires_real_gazebo_capture_before_results(tmp_path: Path) -> None:
    with pytest.raises(REPORT.ReportInputError, match="Gazebo runtime evidence is incomplete"):
        REPORT.build_report_assets(
            stage="test",
            results_path=None,
            statistics_path=None,
            matched_evidence_path=None,
            output_dir=tmp_path / "generated",
            project_root=tmp_path,
        )


def test_result_report_requires_and_cross_checks_all_paired_statistics(tmp_path: Path) -> None:
    results, statistics, evidence = _write_synthetic_report_inputs(tmp_path)
    output = tmp_path / "generated"
    data = REPORT.build_report_assets(
        stage="validation",
        results_path=results,
        statistics_path=statistics,
        matched_evidence_path=evidence,
        output_dir=output,
        project_root=tmp_path,
        expected_conditions=72,
    )

    assert data["schema_version"] == 3
    assert data["condition_count"] == 72
    assert len(data["paired_comparisons"]) == 12
    planner_failure = data["base_pgrr_planner_failure"]
    assert planner_failure["preregistered_inferential_endpoint"] is False
    assert planner_failure["post_hoc_significance_test"] is False
    assert planner_failure["base"]["rate"] == planner_failure["pgrr"]["rate"]
    efficiency = data["base_pgrr_joint_success_efficiency"]
    assert efficiency["population"] == "joint_success"
    assert efficiency["pair_count"] == 42
    assert set(efficiency["metrics"]) == {"duration", "path_length"}
    assert efficiency["metrics"]["path_length"]["difference_pgrr_minus_base"] == pytest.approx(0.4)
    assert len(data["statistics_sha256"]) == 64
    assert (output / "result_paired_effects.pdf").read_bytes().startswith(b"%PDF")
    assert (output / "result_joint_success_efficiency.pdf").read_bytes().startswith(b"%PDF")
    assert (output / "result_matched_run_evidence.pdf").read_bytes().startswith(b"%PDF")
    assert data["matched_run_evidence"]["representation"].startswith("telemetry")
    table = (output / "result_paired_statistics.tex").read_text(encoding="utf-8")
    assert all(label in table for label in ("DWB", "Standard", "Heuristic", "Uniform BC"))
    assert all(label in table for label in ("目标到达", "碰撞", "超时"))
    assert "95\\% CI" in table and "\\mathrm{OR}_H" in table
    macros = (output / "report_stage.tex").read_text(encoding="utf-8")
    assert r"\ReportBasePlannerFailureRate" in macros
    assert r"\ReportPlannerFailureDifference" in macros
    assert r"\newcommand{\ReportJointSuccessPairCount}{42}" in macros
    assert r"\ReportJointSuccessDurationDifference" in macros
    assert r"\ReportJointSuccessPathDifference" in macros

    loaded = DECK.load_report_data(output / "report_data.json", stage="validation")
    specs = DECK.build_slide_specs("validation", loaded)
    slide = specs[23]
    assert slide.asset == "report/generated/result_paired_effects.pdf"
    assert all(
        name in " ".join(slide.bullets) for name in ("DWB", "Standard", "Heuristic", "Uniform BC")
    )
    assert "95% CI" in slide.bullets[-1] and "Holm" in slide.bullets[-1]
    efficiency_slide = specs[24]
    assert efficiency_slide.asset == "report/generated/result_joint_success_efficiency.pdf"
    assert "共同成功条件下" in efficiency_slide.title
    assert any("共同到达 pair" in bullet and "42" in bullet for bullet in efficiency_slide.bullets)
    assert all("如果还是 pending" not in spec.notes for spec in specs)


def test_result_report_rejects_missing_or_tampered_statistics(tmp_path: Path) -> None:
    results, statistics, evidence = _write_synthetic_report_inputs(tmp_path)
    with pytest.raises(REPORT.ReportInputError, match="requires an explicit completed pairwise"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            output_dir=tmp_path / "missing",
            project_root=tmp_path,
            expected_conditions=72,
        )

    payload = json.loads(statistics.read_text(encoding="utf-8"))
    payload["comparisons"]["base"]["binary_outcomes"]["goal_reached"][
        "difference_treatment_minus_reference"
    ]["estimate"] = 0.99
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(REPORT.ReportInputError, match="paired difference disagrees"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            statistics_path=statistics,
            matched_evidence_path=evidence,
            output_dir=tmp_path / "tampered",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_result_report_rejects_tampered_global_holm_adjustment(tmp_path: Path) -> None:
    results, statistics, evidence = _write_synthetic_report_inputs(tmp_path)
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    payload["global_multiple_comparison"]["hypotheses"][0]["pvalue_holm_global"] = 0.0
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(REPORT.ReportInputError, match="global Holm adjustment is inconsistent"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            statistics_path=statistics,
            matched_evidence_path=evidence,
            output_dir=tmp_path / "tampered-holm",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_result_report_rejects_tampered_joint_success_efficiency(tmp_path: Path) -> None:
    results, statistics, evidence = _write_synthetic_report_inputs(tmp_path)
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    interval = payload["comparisons"]["base"]["continuous_metrics"]["successful_path_length_m"][
        "difference_treatment_minus_reference"
    ]
    interval.update({"estimate": 50.0, "lower": 50.0, "upper": 50.0})
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(REPORT.ReportInputError, match="paired difference disagrees"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            statistics_path=statistics,
            matched_evidence_path=evidence,
            output_dir=tmp_path / "tampered-efficiency",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_result_report_rejects_tampered_matched_raw_provenance(tmp_path: Path) -> None:
    results, statistics, evidence = _write_synthetic_report_inputs(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["runs"]["pgrr"]["raw_sha256"] = "f" * 64
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(REPORT.ReportInputError, match="raw_sha256 disagrees"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            statistics_path=statistics,
            matched_evidence_path=evidence,
            output_dir=tmp_path / "tampered-evidence",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_v5_rows_cannot_be_relabelled_as_an_approved_v6_snapshot() -> None:
    results = _synthetic_report_results()
    results["scenario_id"] = results["scenario_id"].str.replace("moderate_v6", "moderate_v5")
    results["pair_id"] = results["pair_id"].str.replace("moderate_v6", "moderate_v5")
    with pytest.raises(REPORT.ReportInputError, match="moderate-v6"):
        REPORT.validate_results(results, stage="validation", expected_conditions=72)


def test_result_validation_requires_one_of_each_method_per_pair() -> None:
    rows: list[dict[str, object]] = []
    for method in REPORT.METHODS:
        rows.append(
            {
                "episode_id": f"head_on_validation_moderate_v6_r00_{method}",
                "pair_id": "head_on_validation_moderate_v6_r00_seed1",
                "scenario_id": "head_on_validation_moderate_v6_r00",
                "family": "head_on_corridor",
                "density": "low",
                "replicate": 0,
                "seed": 1,
                "split": "validation",
                "source_policy": method,
                "outcome": "GOAL_REACHED",
                "raw_sha256": "0" * 64,
                "scenario_sha256": "1" * 64,
                "episode_duration_s": 1.0,
                "navigation_time_s": 1.0,
                "path_length_m": 1.0,
                "min_human_distance_m": 1.0,
                "recovery_trigger_count": 0,
                "recovery_success_count": 0,
                "recovery_duration_s": 0.0,
                "intervention_ratio": 0.0,
            }
        )
    valid = pd.DataFrame(rows)
    REPORT.validate_results(valid, stage="validation", expected_conditions=1)

    duplicate = pd.concat([valid, valid.iloc[[0]]], ignore_index=True)
    with pytest.raises(REPORT.ReportInputError):
        REPORT.validate_results(duplicate, stage="validation", expected_conditions=1)


def test_pending_deck_has_30_substantive_chinese_slides() -> None:
    data = {
        "schema_version": 1,
        "stage": "pending",
        "results_available": False,
        "author_alias": "Charles Chen",
    }
    specs = DECK.build_slide_specs("pending", data)
    DECK.validate_assets(specs, stage="pending")

    assert len(specs) == 30
    assert [spec.number for spec in specs] == list(range(1, 31))
    assert all(spec.title and spec.takeaway and spec.bullets and spec.notes for spec in specs)
    assert all("结果尚未锁定" in specs[index - 1].bullets[0] for index in range(21, 28))
    assert all(spec.asset not in DECK.RESULT_ASSETS for spec in specs if spec.asset)
    assert DECK.PUBLIC_NAME in specs[0].takeaway
    assert "raw/Parquet" in specs[25].takeaway

    titles = {spec.title for spec in specs}
    required_title_fragments = (
        "DWB 在 Nav2 中负责什么",
        "Dynamic Window",
        "DWB 如何选出一条轨迹",
        "Behavior Cloning",
        "DAgger",
        "PGRR 的两轮 DAgger",
    )
    assert all(any(fragment in title for title in titles) for fragment in required_title_fragments)
    algorithm_notes = " ".join(spec.notes for spec in specs[3:20])
    assert "Nav2 官方 DWB Controller 文档" in algorithm_notes
    assert "generator 可插拔" in algorithm_notes
    assert "LimitedAccelGenerator" in algorithm_notes
    assert "https://proceedings.mlr.press/v15/ross11a.html" in algorithm_notes
    source_markers = (
        "https://docs.nav2.org/",
        "https://doi.org/10.1109/100.580977",
        "https://proceedings.mlr.press/v15/ross11a.html",
    )
    assert all(any(marker in spec.notes for marker in source_markers) for spec in specs[2:20])

    notes = DECK.render_notes(specs, stage="pending")
    assert notes.count("\n## ") == 30
    assert "如果还是 pending" in notes
    assert "/home/" not in notes
    required_algorithm_urls = (
        "https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html",
        "https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md",
        "https://doi.org/10.1109/100.580977",
        "https://proceedings.mlr.press/v15/ross11a.html",
    )
    assert all(notes.count(url) >= 1 for url in required_algorithm_urls)


def test_locked_deck_is_figure_led_with_distinct_algorithm_assets() -> None:
    data = json.loads((ROOT / "report/generated/report_data.json").read_text(encoding="utf-8"))
    assert data["stage"] == "test"
    specs = DECK.build_slide_specs("test", data)

    illustrated = [spec for spec in specs if spec.asset is not None]
    unique_assets = {spec.asset for spec in illustrated}
    assert len(illustrated) >= 26
    assert len(unique_assets) >= 18


def test_report_source_is_detailed_and_stage_conditional() -> None:
    source = (ROOT / "report/technical_report.tex").read_text(encoding="utf-8")
    assert source.count(r"\section{") >= 25
    assert source.count(r"\clearpage") >= 25
    assert r"\ifReportResultsAvailable" in source
    assert "runtime_gazebo_doorway_bottleneck_medium.png" in source
    assert "result_matched_run_evidence.pdf" in source
    assert "result_matched_trajectory.pdf" in source
    assert "result_matched_recovery_timeline.pdf" in source
    assert "telemetry reconstruction" in source
    assert "moderate-v6" in source and "moderate-v5" in source
    assert "Planning-Guided Failure-Triggered Recovery and Rejoin" in source
    assert "result_paired_statistics.tex" in source
    assert "result_paired_effects.pdf" in source
    assert "Charles Chen" in source
    assert "/home/" not in source


def test_all_summary_layers_preserve_historical_v1_tradeoff_as_non_v6() -> None:
    paths = (
        ROOT / "README.md",
        ROOT / "REPRODUCIBILITY.md",
        ROOT / "report/technical_report.tex",
        ROOT / "report/README.md",
        ROOT / "presentation/README.md",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert all(token in source for token in ("64/64", "0/24", "19/24", "16/24", "8/24", "5/24"))
        assert "v6" in source
    slide_two = DECK.build_slide_specs(
        "pending",
        {"stage": "pending", "results_available": False, "author_alias": "Charles Chen"},
    )[1]
    summary = " ".join(slide_two.bullets)
    assert all(token in summary for token in ("64/64", "0/24", "19/24", "16/24", "8/24", "5/24"))
    assert "非 v6" in summary and "不显著" in summary


def test_makefile_exposes_report_and_presentation_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "technical-report:" in makefile
    assert "presentation-check:" in makefile
    assert "presentation:" in makefile
    assert "REPORT_STAGE ?= pending" in makefile
    assert "REPORT_STATISTICS ?= outputs/moderate/final/pairwise_statistics.json" in makefile
    assert (
        "REPORT_MATCHED_EVIDENCE ?= outputs/moderate/final/matched_base_pgrr_evidence.json"
        in makefile
    )
    assert '--matched-evidence "$(REPORT_MATCHED_EVIDENCE)"' in makefile
    assert "--require-runtime-capture" in makefile


def test_new_sources_do_not_contain_local_account_or_real_identity() -> None:
    private_root = Path("/").joinpath("home", "diy").as_posix()
    paths = (
        ROOT / "report/technical_report.tex",
        ROOT / "scripts/report/build_report_assets.py",
        ROOT / "scripts/report/build_report.sh",
        ROOT / "scripts/presentation/build_deck.py",
        ROOT / "scripts/presentation/render_pdf.sh",
    )
    for path in paths:
        payload = path.read_text(encoding="utf-8")
        assert private_root not in payload
