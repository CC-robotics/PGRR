from __future__ import annotations

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
            rows.append(
                {
                    "episode_id": f"{pair_id}_{method}",
                    "pair_id": pair_id,
                    "scenario_id": f"fixture_{family}_{density}",
                    "family": family,
                    "density": density,
                    "seed": 810_000 + condition_index,
                    "split": "validation",
                    "source_policy": method,
                    "outcome": outcome,
                    "included_in_algorithm_metrics": True,
                    "episode_duration_s": 40.0 + condition_index,
                    "navigation_time_s": 39.0 + condition_index + method_index,
                    "min_human_distance_m": 0.55 + 0.04 * method_index,
                    "recovery_trigger_count": 0 if method == "base" else 4,
                    "recovery_success_count": 0 if method == "base" else method_index,
                    "recovery_duration_s": 0.5 * method_index,
                    "intervention_ratio": 0.02 * method_index,
                }
            )
    return pd.DataFrame(rows)


def _write_synthetic_report_inputs(tmp_path: Path) -> tuple[Path, Path]:
    directory = tmp_path / "outputs/report_inputs/validation"
    directory.mkdir(parents=True)
    results = _synthetic_report_results()
    results_path = directory / "results.parquet"
    statistics_path = directory / "pairwise_statistics.json"
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
    return results_path, statistics_path


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


def test_result_report_requires_and_cross_checks_all_paired_statistics(tmp_path: Path) -> None:
    results, statistics = _write_synthetic_report_inputs(tmp_path)
    output = tmp_path / "generated"
    data = REPORT.build_report_assets(
        stage="validation",
        results_path=results,
        statistics_path=statistics,
        output_dir=output,
        project_root=tmp_path,
        expected_conditions=72,
    )

    assert data["schema_version"] == 2
    assert data["condition_count"] == 72
    assert len(data["paired_comparisons"]) == 12
    assert len(data["statistics_sha256"]) == 64
    assert (output / "result_paired_effects.pdf").read_bytes().startswith(b"%PDF")
    table = (output / "result_paired_statistics.tex").read_text(encoding="utf-8")
    assert all(label in table for label in ("DWB", "Standard", "Heuristic", "Uniform BC"))
    assert all(label in table for label in ("目标到达", "碰撞", "超时"))
    assert "95\\% CI" in table and "\\mathrm{OR}_H" in table

    loaded = DECK.load_report_data(output / "report_data.json", stage="validation")
    specs = DECK.build_slide_specs("validation", loaded)
    slide = specs[23]
    assert slide.asset == "report/generated/result_paired_effects.pdf"
    assert all(
        name in " ".join(slide.bullets) for name in ("DWB", "Standard", "Heuristic", "Uniform BC")
    )
    assert "95% CI" in slide.bullets[-1] and "Holm" in slide.bullets[-1]


def test_result_report_rejects_missing_or_tampered_statistics(tmp_path: Path) -> None:
    results, statistics = _write_synthetic_report_inputs(tmp_path)
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
            output_dir=tmp_path / "tampered",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_result_report_rejects_tampered_global_holm_adjustment(tmp_path: Path) -> None:
    results, statistics = _write_synthetic_report_inputs(tmp_path)
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    payload["global_multiple_comparison"]["hypotheses"][0]["pvalue_holm_global"] = 0.0
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(REPORT.ReportInputError, match="global Holm adjustment is inconsistent"):
        REPORT.build_report_assets(
            stage="validation",
            results_path=results,
            statistics_path=statistics,
            output_dir=tmp_path / "tampered-holm",
            project_root=tmp_path,
            expected_conditions=72,
        )


def test_result_validation_requires_one_of_each_method_per_pair() -> None:
    rows: list[dict[str, object]] = []
    for method in REPORT.METHODS:
        rows.append(
            {
                "pair_id": "pair-0",
                "scenario_id": "scenario-0",
                "family": "head_on_corridor",
                "density": "low",
                "seed": 1,
                "split": "validation",
                "source_policy": method,
                "outcome": "GOAL_REACHED",
                "episode_duration_s": 1.0,
                "navigation_time_s": 1.0,
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

    notes = DECK.render_notes(specs, stage="pending")
    assert notes.count("\n## ") == 30
    assert "/home/" not in notes


def test_report_source_is_detailed_and_stage_conditional() -> None:
    source = (ROOT / "report/technical_report.tex").read_text(encoding="utf-8")
    assert source.count(r"\section{") >= 25
    assert source.count(r"\clearpage") >= 25
    assert r"\ifReportResultsAvailable" in source
    assert "runtime_gazebo_doorway_bottleneck_medium.png" in source
    assert "result_paired_statistics.tex" in source
    assert "result_paired_effects.pdf" in source
    assert "Charles Chen" in source
    assert "/home/" not in source


def test_makefile_exposes_report_and_presentation_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "technical-report:" in makefile
    assert "presentation-check:" in makefile
    assert "presentation:" in makefile
    assert "REPORT_STAGE ?= pending" in makefile
    assert "REPORT_STATISTICS ?= outputs/moderate/final/pairwise_statistics.json" in makefile


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
