from __future__ import annotations

import hashlib
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pandas as pd
from matplotlib.figure import Figure


def _paper_module(name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[2] / f"scripts/paper/{name}.py"
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


make_figures = _paper_module("make_figures")
make_tables = _paper_module("make_tables")


SCENARIOS = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)


def _result_row(
    *,
    method: str,
    scenario: str,
    density: str,
    outcome: str,
    method_index: int,
) -> dict[str, object]:
    success = outcome == "GOAL_REACHED"
    return {
        "episode_id": f"{scenario}_{density}_{method}",
        # Match the collector's simultaneous aggregate/detail columns.  The
        # figure loader must prefer family and source_policy.
        "scenario_id": f"{scenario}_{density}_test_s1",
        "scenario": f"{scenario}_{density}_test_s1",
        "family": scenario,
        "density": density,
        "seed": 1,
        "source_policy": method,
        "method": method,
        "planner_id": "dwb",
        "project_commit": "abc123",
        "outcome": outcome,
        "navigation_time_s": 72.0 + 8.0 * method_index,
        "spl": 0.72 + 0.04 * method_index if success else 0.0,
        "min_human_distance_m": 0.68 + 0.09 * method_index,
        "recovery_trigger_count": float(method_index > 0),
        "recovery_success_rate": 0.75 if method == "bc" else 0.5,
        "recovery_duration_s": 0.0 if method_index == 0 else 1.2 + method_index,
        "intervention_ratio": 0.0 if method_index == 0 else 0.06 * method_index,
        "emergency_stop_count": float(max(0, 3 - method_index)),
        "progress_m": 4.0 + method_index,
    }


def _write_runtime(raw_dir: Path, episode_id: str, outcome: str = "GOAL_REACHED") -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "timestamp": 0.0,
            "robot_pose": [0.0, 0.0, 0.0],
            "goal": [2.0, 0.0, 0.0],
            "global_path": [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
            "failure_score": 0.1,
            "distance_to_goal": 2.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "privileged": {
                "robot_pose": [0.0, 0.0, 0.0],
                "human_positions": [[0.8, 0.5], [1.3, -0.4]],
            },
        },
        {
            "timestamp": 1.0,
            "robot_pose": [0.45, 0.0, 0.1],
            "goal": [2.0, 0.0, 0.0],
            "global_path": [[0.45, 0.0], [1.0, 0.1], [2.0, 0.0]],
            "failure_score": 0.82,
            "distance_to_goal": 1.55,
            "recovery_state": 2,
            "recovery_action": 3,
            "privileged": {
                "robot_pose": [0.45, 0.0, 0.1],
                "human_positions": [[0.9, 0.25], [1.2, -0.25]],
            },
        },
        {
            "timestamp": 2.0,
            "robot_pose": [1.2, 0.1, -0.05],
            "goal": [2.0, 0.0, 0.0],
            "global_path": [[1.2, 0.1], [2.0, 0.0]],
            "failure_score": 0.3,
            "distance_to_goal": 0.81,
            "recovery_state": 3,
            "recovery_action": 24,
            "privileged": {
                "robot_pose": [1.2, 0.1, -0.05],
                "human_positions": [[0.9, 0.0], [1.1, -0.1]],
            },
        },
        {
            "timestamp": 3.0,
            "robot_pose": [2.0, 0.0, 0.0],
            "goal": [2.0, 0.0, 0.0],
            "global_path": [[2.0, 0.0]],
            "failure_score": 0.05,
            "distance_to_goal": 0.0,
            "recovery_state": 6,
            "recovery_action": 24,
            "privileged": {
                "robot_pose": [2.0, 0.0, 0.0],
                "human_positions": [[0.8, -0.2], [1.0, 0.15]],
            },
        },
    ]
    stream = raw_dir / f"{episode_id}.jsonl"
    stream.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    stream.with_suffix(".metadata.json").write_text(
        json.dumps({"episode_id": episode_id, "project_commit": "abc123"}),
        encoding="utf-8",
    )
    stream.with_suffix(".outcome.json").write_text(
        json.dumps({"episode_id": episode_id, "outcome": outcome}),
        encoding="utf-8",
    )


def _statistics_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "reference_policy": "base",
        "treatment_policy": "bc",
        "binary_outcomes": {
            "goal_reached": {
                "pair_count": 24,
                "difference_treatment_minus_reference": {
                    "estimate": 0.5,
                    "lower": 0.2,
                    "upper": 0.8,
                },
                "mcnemar_exact": {
                    "pvalue_raw": 0.012,
                    "pvalue_holm": 0.024,
                    "matched_odds_ratio_haldane": 0.5,
                },
            },
            "collision": {
                "pair_count": 24,
                "difference_treatment_minus_reference": {
                    "estimate": -0.25,
                    "lower": -0.45,
                    "upper": -0.05,
                },
                "mcnemar_exact": {
                    "pvalue_raw": 0.02,
                    "pvalue_holm": 0.04,
                    "matched_odds_ratio_haldane": 0.2,
                },
            },
            "timeout": {
                "pair_count": 24,
                "difference_treatment_minus_reference": {
                    "estimate": -0.1,
                    "lower": -0.25,
                    "upper": 0.0,
                },
                "mcnemar_exact": {
                    "pvalue_raw": 0.08,
                    "pvalue_holm": 0.12,
                    "matched_odds_ratio_haldane": 0.4,
                },
            },
        },
        "continuous_metrics": {
            "min_human_distance_m": {
                "status": "ok",
                "pair_count": 24,
                "difference_treatment_minus_reference": {
                    "estimate": 0.27,
                    "lower": 0.11,
                    "upper": 0.39,
                },
                "wilcoxon": {"pvalue_raw": 0.0004, "pvalue_holm": 0.0012},
                "effect_size": {"rank_biserial_correlation": 0.63},
            },
            "successful_episode_duration_s": {
                "status": "ok",
                "pair_count": 16,
                "difference_treatment_minus_reference": {
                    "estimate": 4.0,
                    "lower": 1.0,
                    "upper": 7.0,
                },
                "wilcoxon": {"pvalue_raw": 0.03, "pvalue_holm": 0.06},
                "effect_size": {"rank_biserial_correlation": 0.4},
            },
        },
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ablation(root: Path) -> Path:
    dataset = root / "data/interim/fixture.h5"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_bytes(b"held-out validation states")
    dataset_name = "data/interim/fixture.h5"
    rows: list[dict[str, object]] = []
    models = (
        ("Uniform BC", "checkpoints/bc/uniform.pt", 0.8847, 0.2711, 0.9323),
        ("Margin-weighted BC", "checkpoints/bc/mwbc.pt", 0.8847, 0.2711, 0.9323),
        ("Triggered DAgger", "checkpoints/dagger/best.pt", 0.9223, 0.0310, 0.8396),
    )
    for model, checkpoint_name, top1, regret, disabled_invalid in models:
        checkpoint = root / checkpoint_name
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(model.encode("utf-8"))
        common = {
            "model": model,
            "checkpoint": checkpoint_name,
            "checkpoint_sha256": _digest(checkpoint),
            "dataset": dataset_name,
            "dataset_sha256": _digest(dataset),
            "parameter_count": 59193,
            "sample_count": 399,
        }
        rows.append(
            {
                **common,
                "action_mask": "enabled",
                "top1_accuracy": top1,
                "top3_accuracy": 0.98,
                "invalid_action_rate": 0.0,
                "expert_cost_regret": regret,
                "near_optimal_rate": 0.93,
                "catastrophic_action_rate": 0.0,
            }
        )
        rows.append(
            {
                **common,
                "action_mask": "disabled_offline",
                "top1_accuracy": 1.0 - disabled_invalid,
                "top3_accuracy": 0.4,
                "invalid_action_rate": disabled_invalid,
                "expert_cost_regret": 1_000_000.0 * disabled_invalid,
                "near_optimal_rate": 0.1,
                "catastrophic_action_rate": disabled_invalid,
            }
        )
    ablation = root / "outputs/final/offline_policy_ablation.csv"
    pd.DataFrame(rows).to_csv(ablation, index=False)
    ablation.with_suffix(".json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset": dataset_name,
                "dataset_sha256": _digest(dataset),
                "sample_count": 399,
                "output": "outputs/final/offline_policy_ablation.csv",
                "output_sha256": _digest(ablation),
                "note": (
                    "Mask-disabled rows are offline proposals and were never executed on the robot."
                ),
            }
        ),
        encoding="utf-8",
    )
    return ablation


def _write_final_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    rows: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        for density in ("low", "medium", "high"):
            base_outcome = "COLLISION" if density == "high" else "GOAL_REACHED"
            rows.append(
                _result_row(
                    method="base",
                    scenario=scenario,
                    density=density,
                    outcome=base_outcome,
                    method_index=0,
                )
            )
            rows.append(
                _result_row(
                    method="bc",
                    scenario=scenario,
                    density=density,
                    outcome="GOAL_REACHED",
                    method_index=3,
                )
            )
            if density == "high":
                rows.append(
                    _result_row(
                        method="standard",
                        scenario=scenario,
                        density=density,
                        outcome="TIMEOUT",
                        method_index=1,
                    )
                )
                rows.append(
                    _result_row(
                        method="heuristic",
                        scenario=scenario,
                        density=density,
                        outcome="GOAL_REACHED",
                        method_index=2,
                    )
                )

    final_dir = root / "outputs/final"
    results = final_dir / "results.parquet"
    summary = final_dir / "summary.csv"
    statistics = final_dir / "statistics.json"
    raw_dir = root / "data/raw"
    final_dir.mkdir(parents=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(results, index=False)

    method_rows = [
        {
            "row_type": "method_summary",
            "project_commit": "abc123",
            "method": method,
            "excluded_attempt_count": {"base": 1, "bc": 2}.get(method, 0),
        }
        for method in ("base", "bc", "standard", "heuristic")
    ]
    paired_rows = [
        {
            "row_type": "statistic",
            "project_commit": "abc123",
            "comparison": "DWB vs Triggered DAgger",
            "metric": "goal_reached",
            "test": "McNemar exact",
            "estimate": 0.5,
            "ci_low": 0.2,
            "ci_high": 0.8,
            "p_value": 0.012,
            "p_value_holm": 0.024,
            "effect_size": 0.5,
            "n_pairs": 24,
        },
        {
            "row_type": "statistic",
            "project_commit": "abc123",
            "comparison": "DWB vs Triggered DAgger",
            "metric": "min_human_distance_m",
            "test": "Wilcoxon signed-rank",
            "estimate": 0.27,
            "ci_low": 0.11,
            "ci_high": 0.39,
            "p_value": 0.0004,
            "p_value_holm": 0.0012,
            "effect_size": 0.63,
            "n_pairs": 24,
        },
        {
            "row_type": "statistic",
            "project_commit": "abc123",
            "comparison": "DWB vs Triggered DAgger",
            "metric": "collision",
            "test": "McNemar exact",
            "estimate": -0.25,
            "ci_low": -0.45,
            "ci_high": -0.05,
            "p_value": 0.02,
            "p_value_holm": 0.04,
            "effect_size": 0.2,
            "n_pairs": 24,
        },
        {
            "row_type": "statistic",
            "project_commit": "abc123",
            "comparison": "DWB vs Triggered DAgger",
            "metric": "timeout",
            "test": "McNemar exact",
            "estimate": -0.1,
            "ci_low": -0.25,
            "ci_high": 0.0,
            "p_value": 0.08,
            "p_value_holm": 0.12,
            "effect_size": 0.4,
            "n_pairs": 24,
        },
        {
            "row_type": "statistic",
            "project_commit": "abc123",
            "comparison": "DWB vs Triggered DAgger",
            "metric": "successful_episode_duration_s",
            "test": "Wilcoxon signed-rank",
            "estimate": 4.0,
            "ci_low": 1.0,
            "ci_high": 7.0,
            "p_value": 0.03,
            "p_value_holm": 0.06,
            "effect_size": 0.4,
            "n_pairs": 16,
        },
    ]
    pd.DataFrame([*method_rows, *paired_rows]).to_csv(summary, index=False)
    statistics.write_text(json.dumps(_statistics_payload()), encoding="utf-8")

    selected_id = "blind_corner_high_bc"
    _write_runtime(raw_dir, selected_id)
    ablation = _write_ablation(root)
    return results, summary, statistics, raw_dir, ablation


def test_final_fixture_generates_type42_figures_and_latex(tmp_path: Path) -> None:
    results, summary, statistics, raw_dir, ablation = _write_final_fixture(tmp_path)
    figure_dir = tmp_path / "paper/figures"
    table_dir = tmp_path / "paper/generated"

    figures = make_figures.generate_figures(
        results,
        summary,
        figure_dir,
        raw_dir,
        statistics,
    )
    tables = make_tables.generate_tables(results, summary, table_dir, statistics, ablation)

    assert {path.name for path in figures} == {
        "system_architecture.pdf",
        "action_space_expert.pdf",
        "final_scenario_montage.pdf",
        "final_outcomes_by_density.pdf",
        "final_safety_efficiency.pdf",
        "final_recovery_timeline.pdf",
        "runtime_sequence.pdf",
    }
    assert {path.name for path in tables} == {
        "main_results.tex",
        "density_results.tex",
        "recovery_metrics.tex",
        "statistical_results.tex",
        "offline_ablation.tex",
        "result_macros.tex",
    }
    for figure in figures:
        payload = figure.read_bytes()
        assert payload.startswith(b"%PDF")
        assert b"/Subtype /Type3" not in payload
    main_table = (table_dir / "main_results.tex").read_text(encoding="utf-8")
    density_table = (table_dir / "density_results.tex").read_text(encoding="utf-8")
    recovery_table = (table_dir / "recovery_metrics.tex").read_text(encoding="utf-8")
    statistics_table = (table_dir / "statistical_results.tex").read_text(encoding="utf-8")
    assert "outputs/pilot" not in main_table
    assert "project_commit=abc123" in main_table
    assert "PGRR" in main_table
    assert "excluded from algorithm rates" in main_table
    assert "DWB & 24" in main_table and "& 1 \\\\" in main_table
    assert "McNemar" in statistics_table
    assert "$<0.001$" in statistics_table
    assert "DWB vs PGRR" in statistics_table
    assert "Min. human distance" in statistics_table
    assert r"$+50.0\;[+20.0,\,+80.0]\,\mathrm{pp}$" in statistics_table
    assert r"\mathrm{OR}_H" in statistics_table
    assert r"r_{\mathrm{rb}}" in statistics_table
    assert r"p_{\mathrm{raw}}" in statistics_table
    assert r"p_{\mathrm{Holm}}" in statistics_table
    offline_table = (table_dir / "offline_ablation.tex").read_text(encoding="utf-8")
    macros = (table_dir / "result_macros.tex").read_text(encoding="utf-8")
    assert "never executed" in offline_table
    assert "399 scenario-disjoint" in offline_table
    assert r"\providecommand{\PGRRMainPairCount}{24}" in macros
    assert r"\providecommand{\PGRRSuccessDifference}" in macros

    for table in (
        main_table,
        density_table,
        recovery_table,
        statistics_table,
        offline_table,
    ):
        # IEEE/CVPR-style tables use booktabs, compact edge spacing, and no
        # vertical rules or scale-to-fit typography.
        assert all(rule in table for rule in (r"\toprule", r"\midrule", r"\bottomrule"))
        tabular_spec = table.split(r"\begin{tabular}{", maxsplit=1)[1].split("}", maxsplit=1)[0]
        assert "|" not in tabular_spec
        assert tabular_spec.startswith("@{")
        assert r"\resizebox" not in table
        assert r"\setlength{\tabcolsep}" in table
        assert r"\renewcommand{\arraystretch}" in table

    assert r"\textbf{PGRR}" in main_table
    assert "Timeout" in main_table and "Timeout" in density_table
    assert "success-conditional metrics" in statistics_table


def test_action_space_expert_explanation_does_not_overlap(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    captured: dict[str, Figure] = {}

    def capture_figure(figure: Figure, _output: Path) -> None:
        captured["figure"] = figure

    monkeypatch.setattr(make_figures, "_save_pdf", capture_figure)  # type: ignore[attr-defined]
    make_figures.action_space_expert_figure(tmp_path / "action_space_expert.pdf")

    figure = captured["figure"]
    figure.canvas.draw()
    explanation_axis = figure.axes[1]
    renderer = figure.canvas.get_renderer()
    rollout_text = next(item for item in explanation_axis.texts if "rollout" in item.get_text())
    cost_text = next(item for item in explanation_axis.texts if item.get_text().startswith("$J"))
    legend_texts = [
        next(item for item in explanation_axis.texts if item.get_text() == label)
        for label in (
            "valid candidate",
            "masked candidate",
            "minimum-cost valid action",
        )
    ]
    rollout_bounds = rollout_text.get_window_extent(renderer)
    cost_bounds = cost_text.get_window_extent(renderer)
    legend_bounds = [item.get_window_extent(renderer) for item in legend_texts]

    assert rollout_bounds.y0 >= cost_bounds.y1 + 3.0
    assert cost_bounds.y0 >= legend_bounds[0].y1 + 3.0
    assert legend_bounds[0].y0 >= legend_bounds[1].y1 + 1.0
    assert legend_bounds[1].y0 >= legend_bounds[2].y1 + 1.0
    make_figures.plt.close(figure)


def test_missing_final_artifacts_fail_without_pilot_fallback(
    tmp_path: Path,
    capsys: object,
) -> None:
    exit_code = make_figures.main(
        [
            "--results",
            str(tmp_path / "missing.parquet"),
            "--summary",
            str(tmp_path / "missing.csv"),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--output-dir",
            str(tmp_path / "figures"),
        ]
    )
    assert exit_code != 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "No pilot fallback is permitted" in captured.err
    assert not (tmp_path / "figures").exists()


def test_mixed_project_commits_are_rejected(tmp_path: Path) -> None:
    results_path, summary_path, _, _, _ = _write_final_fixture(tmp_path)
    results = pd.read_parquet(results_path)
    results.loc[0, "project_commit"] = "different"
    results.to_parquet(results_path, index=False)

    try:
        make_figures.load_final_artifacts(results_path, summary_path)
    except make_figures.ArtifactError as error:
        assert "mix project commits" in str(error)
    else:  # pragma: no cover - makes the failure message explicit
        raise AssertionError("mixed final commits were accepted")


def test_runtime_jsonl_is_required(tmp_path: Path) -> None:
    results, summary, statistics, raw_dir, _ = _write_final_fixture(tmp_path)
    for path in raw_dir.iterdir():
        path.unlink()
    try:
        make_figures.generate_figures(
            results,
            summary,
            tmp_path / "figures",
            raw_dir,
            statistics,
        )
    except make_figures.ArtifactError as error:
        assert "no raw JSONL" in str(error)
    else:  # pragma: no cover
        raise AssertionError("paper figures were generated without raw runtime evidence")


def test_high_density_subset_must_match_and_be_contained(tmp_path: Path) -> None:
    results_path, summary_path, _, _, _ = _write_final_fixture(tmp_path)
    results = pd.read_parquet(results_path)
    target = results.index[results["source_policy"] == "heuristic"][0]
    results.loc[target, "density"] = "medium"
    results.to_parquet(results_path, index=False)
    try:
        make_figures.load_final_artifacts(results_path, summary_path)
    except make_figures.ArtifactError as error:
        assert "high-density subset" in str(error) or "subset" in str(error)
    else:  # pragma: no cover
        raise AssertionError("mismatched standard/heuristic subset was accepted")


def test_statistics_json_disagreement_is_rejected(tmp_path: Path) -> None:
    results, summary, statistics, _, _ = _write_final_fixture(tmp_path)
    payload = json.loads(statistics.read_text(encoding="utf-8"))
    payload["binary_outcomes"]["goal_reached"]["mcnemar_exact"]["pvalue_holm"] = 0.9
    statistics.write_text(json.dumps(payload), encoding="utf-8")
    try:
        make_figures.load_final_artifacts(results, summary, statistics)
    except make_figures.ArtifactError as error:
        assert "disagree" in str(error)
    else:  # pragma: no cover
        raise AssertionError("disagreeing statistics artifacts were accepted")


def test_offline_ablation_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    _, _, _, _, ablation = _write_final_fixture(tmp_path)
    ablation.write_text(ablation.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    try:
        make_tables.load_offline_ablation(ablation)
    except make_figures.ArtifactError as error:
        assert "hash mismatch" in str(error)
    else:  # pragma: no cover
        raise AssertionError("tampered ablation CSV was accepted")


def test_result_macros_require_all_primary_paired_metrics(tmp_path: Path) -> None:
    results, summary, _, _, _ = _write_final_fixture(tmp_path)
    summary_frame = pd.read_csv(summary)
    summary_frame = summary_frame.loc[summary_frame["metric"] != "timeout"]
    summary_frame.to_csv(summary, index=False)
    loaded_results, loaded_summary = make_figures.load_final_artifacts(results, summary)
    try:
        make_tables.result_macros(
            loaded_results,
            loaded_summary,
            results_path=results,
            summary_path=summary,
            output=tmp_path / "macros.tex",
        )
    except make_figures.ArtifactError as error:
        assert "timeout" in str(error)
    else:  # pragma: no cover
        raise AssertionError("result macros silently omitted a primary metric")


def test_union_summary_accepts_paired_test_row_type(tmp_path: Path) -> None:
    results, summary, _, _, _ = _write_final_fixture(tmp_path)
    frame = pd.read_csv(summary)
    frame.loc[frame["row_type"] == "statistic", "row_type"] = "paired_test"
    frame.to_csv(summary, index=False)
    _, paired = make_figures.load_final_artifacts(results, summary)
    assert set(paired["metric"]) == {
        "goal_reached",
        "collision",
        "timeout",
        "successful_episode_duration_s",
        "min_human_distance_m",
    }
