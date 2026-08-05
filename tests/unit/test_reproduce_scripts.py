from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_reproduction_scripts_are_executable_and_relocatable() -> None:
    for name in ("reproduce_small.sh", "reproduce_paper.sh"):
        path = ROOT / "scripts" / name
        source = _source(name)
        assert os.access(path, os.X_OK)
        assert "BASH_SOURCE[0]" in source
        assert "SCRIPT_DIR}/.." in source
        assert "/home/" not in source
        assert "${HOME}/RAMP" not in source
        assert "rm -rf" not in source


def test_small_reproduction_runs_offline_checks_and_has_a_safe_final_gate() -> None:
    source = _source("reproduce_small.sh")
    assert "pytest -q" in source
    assert "offline_policy_ablation.py" in source
    assert "outputs/smoke/offline_policy_ablation.csv" in source
    assert "--output outputs/final/offline_policy_ablation.csv" not in source
    assert "episode_manifest.parquet" in source
    assert "run_manifest.json" in source
    assert "SKIP final paper chain" in source
    assert "BOOTSTRAP_SEED=20260804" in source
    assert '--bootstrap-seed "${BOOTSTRAP_SEED}"' in source
    assert "collect_results.py" in source
    assert "make_figures.py" in source
    assert "make_tables.py" in source
    assert "build_paper.sh" in source


def test_make_statistics_uses_the_frozen_collector_contract() -> None:
    source = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = source.split("statistics:", maxsplit=1)[1].split("figures:", maxsplit=1)[0]
    assert "collect_results.py" in target
    assert '--manifest "$(MODERATE_ANALYSIS_DIR)/episode_manifest.parquet"' in target
    assert '--run-manifest "$(MODERATE_ANALYSIS_DIR)/run_manifest.json"' in target
    assert '--results "$(MODERATE_RESULTS)"' in target
    assert '--summary "$(MODERATE_ANALYSIS_DIR)/collector_summary.csv"' in target
    assert '--statistics "$(MODERATE_ANALYSIS_DIR)/collector_statistics.json"' in target
    assert "summarize_moderate.py" in target
    assert "--methods $(MODERATE_METHODS)" in target
    assert '--main-method "$(MODERATE_MAIN_METHOD)"' in target
    assert '--reference-method "$(MODERATE_REFERENCE_METHOD)"' in target
    assert '--bootstrap-seed "$(BOOTSTRAP_SEED)"' in target
    assert "BOOTSTRAP_SEED ?= 20260804" in source


def test_paper_reproduction_consumes_artifacts_without_running_simulation() -> None:
    source = _source("reproduce_paper.sh")
    assert "collect_results.py" in source
    assert "summarize_moderate.py" in source
    assert "failure_analysis.py" in source
    assert "render_episode_media.py" in source
    assert "make_method_figures.py" in source
    assert "make_moderate_figures.py" in source
    assert "make_moderate_tables.py" in source
    assert "make_figures.py" not in source
    assert "make_tables.py" not in source
    assert "build_paper.sh" in source
    assert "build_artifact_manifest.py" in source
    assert "outputs/moderate/final" in source
    assert "MODERATE_EXPECTED_CONDITIONS:-120" in source
    assert "METHODS=(base standard heuristic bc_uniform pgrr)" in source
    assert "--main-method pgrr" in source
    assert "--bootstrap-seed 20260804" in source
    assert "run_experiment.py" not in source
    assert "run_baseline.py" not in source
    assert "smoke_arena.sh" not in source

    stages = (
        "collect_results.py",
        "summarize_moderate.py",
        "make_method_figures.py",
        "make_moderate_figures.py",
        "make_moderate_tables.py",
        "build_paper.sh",
    )
    offsets = [source.index(stage) for stage in stages]
    assert offsets == sorted(offsets)


def test_paper_build_checks_overfull_boxes_and_embedded_fonts() -> None:
    source = (ROOT / "scripts" / "paper" / "build_paper.sh").read_text(encoding="utf-8")
    assert "moderate_result_macros.tex" in source
    assert "moderate_outcomes_and_density.pdf" in source
    assert "make_figures.py" not in source
    assert "make_tables.py" not in source
    assert "grep -Fq 'Overfull \\hbox' main.log" in source
    assert 'NR > 2 && $4 == "no"' in source
    assert "$(NF-4)" not in source
