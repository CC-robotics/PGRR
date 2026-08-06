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
    )
    for path in forbidden:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"forbidden")
        with pytest.raises(REPORT.ReportInputError):
            REPORT.validate_result_path(path, stage="test", project_root=tmp_path)


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
    assert "Charles Chen" in source
    assert "/home/" not in source


def test_makefile_exposes_report_and_presentation_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "technical-report:" in makefile
    assert "presentation-check:" in makefile
    assert "presentation:" in makefile
    assert "REPORT_STAGE ?= pending" in makefile


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
