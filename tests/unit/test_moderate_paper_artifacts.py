"""Tests for the moderate paper pipeline using synthetic test-only fixtures."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str) -> ModuleType:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


moderate_artifacts = _load("moderate_artifacts", "scripts/paper/moderate_artifacts.py")
make_figures = _load("make_moderate_figures", "scripts/paper/make_moderate_figures.py")
make_tables = _load("make_moderate_tables", "scripts/paper/make_moderate_tables.py")
summarize = _load("summarize_moderate_paper_fixture", "scripts/evaluate/summarize_moderate.py")

METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
FAMILIES = tuple(moderate_artifacts.FAMILY_ORDER)
DENSITIES = ("low", "medium", "high")
EXPECTED_CONDITION_COUNT = len(FAMILIES) * len(DENSITIES)
SYNTHETIC_PROJECT_COMMIT = "a" * 40


def _synthetic_test_outcomes(method: str) -> list[str]:
    """Return declared test data; values are never used as paper evidence."""

    payload = {
        "base": ["GOAL_REACHED"] * 15 + ["COLLISION"] * 4 + ["TIMEOUT"] * 4 + ["PLANNER_FAILURE"],
        "standard": ["GOAL_REACHED"] * 16
        + ["COLLISION"] * 3
        + ["TIMEOUT"] * 4
        + ["PLANNER_FAILURE"],
        "heuristic": ["GOAL_REACHED"] * 17
        + ["COLLISION"] * 3
        + ["TIMEOUT"] * 3
        + ["PLANNER_FAILURE"],
        "bc_uniform": ["GOAL_REACHED"] * 18
        + ["COLLISION"] * 2
        + ["TIMEOUT"] * 3
        + ["PLANNER_FAILURE"],
        "pgrr": ["GOAL_REACHED"] * 20 + ["COLLISION"] * 2 + ["TIMEOUT"] + ["PLANNER_FAILURE"],
    }
    return payload[method]


def _synthetic_test_results() -> pd.DataFrame:
    """Build a complete five-method fixture explicitly scoped to unit tests."""

    conditions = [
        (family, density, repeat)
        for family in FAMILIES
        for density in DENSITIES
        for repeat in range(1)
    ]
    rows: list[dict[str, Any]] = []
    for method_index, method in enumerate(METHODS):
        for condition_index, ((family, density, repeat), outcome) in enumerate(
            zip(conditions, _synthetic_test_outcomes(method), strict=True)
        ):
            seed = 700_000 + condition_index
            pair_id = f"synthetic_test_{family}_{density}_r{repeat}_s{seed}"
            success = outcome == "GOAL_REACHED"
            recovery_trigger_count = 0 if method == "base" else 4
            recovery_success_count = 0 if method == "base" else method_index
            rows.append(
                {
                    "episode_id": f"{pair_id}_{method}",
                    "pair_id": pair_id,
                    "scenario_id": pair_id,
                    "replicate": repeat,
                    "family": family,
                    "density": density,
                    "seed": seed,
                    "split": "test",
                    "source_policy": method,
                    "outcome": outcome,
                    "included_in_algorithm_metrics": True,
                    "project_commit": SYNTHETIC_PROJECT_COMMIT,
                    "episode_duration_s": 45.0 + condition_index + method_index,
                    "navigation_time_s": 45.0 + condition_index + method_index,
                    "path_length_m": 8.0 + 0.1 * condition_index + 0.05 * method_index,
                    "spl": (0.62 + 0.04 * method_index) if success else 0.0,
                    "min_human_distance_m": 0.55 + 0.04 * method_index + 0.01 * repeat,
                    "human_distance_coverage_ratio": 1.0,
                    "personal_space_violation_ratio": 0.16 - 0.015 * method_index,
                    "discomfort_time_s": 3.0 - 0.25 * method_index + 0.02 * repeat,
                    "emergency_stop_count": float((condition_index + method_index) % 3),
                    "recovery_trigger_count": recovery_trigger_count,
                    "recovery_success_count": recovery_success_count,
                    "recovery_success_rate": (
                        float("nan")
                        if method == "base"
                        else recovery_success_count / recovery_trigger_count
                    ),
                    "recovery_duration_s": float(method_index) * (0.7 + 0.1 * repeat),
                    "intervention_ratio": 0.025 * method_index,
                    "mean_abs_angular_jerk_rad_s3": 0.30 - 0.02 * method_index,
                }
            )
    return pd.DataFrame(rows)


def _write_synthetic_test_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    results = _synthetic_test_results()
    results_path = tmp_path / "synthetic_test_results.parquet"
    summary_path = tmp_path / "synthetic_test_summary.csv"
    statistics_path = tmp_path / "synthetic_test_pairwise_statistics.json"
    results.to_parquet(results_path, index=False)
    summarize.build_summary(results, methods=METHODS).to_csv(summary_path, index=False)
    statistics = summarize.build_pairwise_statistics(
        results,
        methods=METHODS,
        main_method="pgrr",
        reference_method="base",
        bootstrap_samples=40,
        bootstrap_seed=37,
    )
    statistics_path.write_text(
        json.dumps(statistics, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return results_path, summary_path, statistics_path


def test_synthetic_test_fixture_generates_vector_figures_and_booktabs(
    tmp_path: Path,
) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    figure_dir = tmp_path / "figures"
    table_dir = tmp_path / "tables"

    figures = make_figures.generate_moderate_figures(
        results,
        summary,
        statistics,
        figure_dir,
        expected_condition_count=EXPECTED_CONDITION_COUNT,
    )
    tables = make_tables.generate_moderate_tables(
        results,
        summary,
        statistics,
        table_dir,
        expected_condition_count=EXPECTED_CONDITION_COUNT,
    )

    assert {path.name for path in figures} == {
        "moderate_outcomes_and_density.pdf",
        "moderate_family_success.pdf",
        "moderate_paired_effects.pdf",
        "moderate_safety_efficiency.pdf",
    }
    assert {path.name for path in tables} == {
        "moderate_main_results.tex",
        "moderate_density_results.tex",
        "moderate_recovery_metrics.tex",
        "moderate_pairwise_statistics.tex",
        "moderate_result_macros.tex",
    }
    for figure in figures:
        payload = figure.read_bytes()
        assert payload.startswith(b"%PDF")
        assert b"/Subtype /Type3" not in payload
    for table in tables:
        payload = table.read_text(encoding="utf-8")
        assert str(tmp_path) not in payload
        assert "/home/" not in payload

    main = (table_dir / "moderate_main_results.tex").read_text(encoding="utf-8")
    density = (table_dir / "moderate_density_results.tex").read_text(encoding="utf-8")
    pairwise = (table_dir / "moderate_pairwise_statistics.tex").read_text(encoding="utf-8")
    macros = (table_dir / "moderate_result_macros.tex").read_text(encoding="utf-8")
    for method in ("DWB", "Standard", "Heuristic", "Uniform BC", "PGRR"):
        assert method in main
    assert "Timeout" in main and "Timeout" in density and "Timeout" in pairwise
    assert "Planner fail" in main and "Planner fail" in density
    assert "95\\% Wilson" in main
    assert "global family" in pairwise
    assert "McNemar" in pairwise and "Wilcoxon" in pairwise
    assert r"\mathrm{OR}_H" in pairwise and r"r_{\mathrm{rb}}" in pairwise
    assert r"\providecommand{\ModerateMethodCount}{5}" in macros
    assert rf"\providecommand{{\ModeratePairCount}}{{{EXPECTED_CONDITION_COUNT}}}" in macros
    assert r"\textbf{PGRR}" in main
    for table in (main, density, pairwise):
        assert all(rule in table for rule in (r"\toprule", r"\midrule", r"\bottomrule"))
        tabular = table.split(r"\begin{tabular}{", maxsplit=1)[1].split("}", maxsplit=1)[0]
        assert "|" not in tabular
        assert r"\resizebox" not in table


def test_summary_count_tampering_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_csv(summary)
    frame.loc[0, "outcome_count"] = int(frame.loc[0, "outcome_count"]) + 1
    frame.to_csv(summary, index=False)
    with pytest.raises(
        moderate_artifacts.ModerateArtifactError,
        match="outcome_count disagrees",
    ):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_missing_baseline_or_statistics_comparison_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    frame = frame.loc[frame["source_policy"] != "bc_uniform"]
    frame.to_parquet(results, index=False)
    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="exactly the registered"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )

    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path / "second")
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    del payload["comparisons"]["standard"]
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="all four baselines"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_statistics_effect_tampering_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    payload["comparisons"]["base"]["binary_outcomes"]["goal_reached"][
        "difference_treatment_minus_reference"
    ]["estimate"] = 0.99
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="does not contain estimate"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_non_test_split_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    frame["split"] = "validation"
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="require exactly the test"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        (None, "null project_commit"),
        ("abc123", "uniform nonempty 40-hex project_commit"),
        ("b" * 40, "uniform nonempty 40-hex project_commit"),
    ],
)
def test_partial_null_or_mixed_project_commit_is_rejected(
    tmp_path: Path,
    replacement: str | None,
    match: str,
) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    frame.loc[0, "project_commit"] = replacement
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match=match):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_pair_metadata_mismatch_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    row = frame.index[frame["source_policy"] == "base"][0]
    frame.loc[row, "family"] = "doorway_bottleneck"
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="pair metadata mismatch"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_unknown_density_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    frame.loc[0, "density"] = "extreme"
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="low/medium/high density"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_duplicate_episode_id_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    frame.loc[1, "episode_id"] = frame.loc[0, "episode_id"]
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="globally unique"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_declared_condition_count_mismatch_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    with pytest.raises(moderate_artifacts.ModerateArtifactError, match="condition count disagrees"):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT * 2,
        )


@pytest.mark.parametrize(
    ("column", "replacement", "match"),
    [
        ("navigation_time_s", float("nan"), "finite navigation_time_s"),
        ("min_human_distance_m", -0.1, "negative min_human_distance_m"),
        ("spl", 1.1, "spl outside"),
        ("recovery_success_rate", 0.9, "disagrees with recovery success/trigger"),
    ],
)
def test_invalid_publication_metric_is_rejected(
    tmp_path: Path,
    column: str,
    replacement: float,
    match: str,
) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    frame = pd.read_parquet(results)
    row = frame.index[frame["source_policy"] == "standard"][0]
    frame.loc[row, column] = replacement
    frame.to_parquet(results, index=False)

    with pytest.raises(moderate_artifacts.ModerateArtifactError, match=match):
        moderate_artifacts.load_moderate_artifacts(
            results,
            summary,
            statistics,
            expected_condition_count=EXPECTED_CONDITION_COUNT,
        )


def test_timeout_remains_a_distinct_outcome_in_rendered_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results, summary, statistics = _write_synthetic_test_artifacts(tmp_path)
    loaded, _, _ = moderate_artifacts.load_moderate_artifacts(
        results,
        summary,
        statistics,
        expected_condition_count=EXPECTED_CONDITION_COUNT,
    )
    captured: dict[str, Any] = {}

    def capture(figure: Any, _output: Path) -> None:
        captured["figure"] = figure

    monkeypatch.setattr(make_figures, "_save_pdf", capture)
    make_figures.outcome_and_density_figure(loaded, tmp_path / "unused.pdf")
    figure = captured["figure"]
    labels = [text.get_text() for text in figure.texts]
    legend_labels = [
        text.get_text()
        for axis in figure.axes
        for legend in ([axis.get_legend()] if axis.get_legend() is not None else [])
        for text in legend.get_texts()
    ]
    assert "Timeout" in legend_labels
    assert any("timeout" in label.lower() for label in labels)
    make_figures.plt.close(figure)
