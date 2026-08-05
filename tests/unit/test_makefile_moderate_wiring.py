"""Regression tests for strict moderate-publication Make targets."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _dry_run(target: str, *, expected_conditions: int | None = None) -> str:
    command = ["make", "--no-print-directory", "-n", target]
    if expected_conditions is not None:
        command.append(f"MODERATE_EXPECTED_CONDITIONS={expected_conditions}")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def test_moderate_targets_forward_default_expected_condition_count() -> None:
    for target in ("moderate-figures", "moderate-tables"):
        command = _dry_run(target)
        assert '--expected-condition-count "120"' in command


def test_moderate_targets_forward_expected_condition_count_override() -> None:
    for target in ("moderate-figures", "moderate-tables"):
        command = _dry_run(target, expected_conditions=72)
        assert '--expected-condition-count "72"' in command
        assert '--expected-condition-count "120"' not in command


def test_final_runner_uses_real_python_entrypoint_and_five_methods() -> None:
    command = _dry_run("evaluate-flatland")
    assert "scripts/evaluate/run_experiment.py" in command
    assert "scripts/evaluate/run_experiment.sh" not in command
    assert '--split-manifest "scenarios/splits/moderate_v4_test.yaml"' in command
    assert "--methods base standard heuristic bc_uniform pgrr" in command
    assert '--output-dir "outputs/moderate/final"' in command


def test_paper_target_orders_complete_moderate_pipeline() -> None:
    command = _dry_run("paper")
    stages = (
        "scripts/evaluate/collect_results.py",
        "scripts/evaluate/summarize_moderate.py",
        "scripts/paper/make_moderate_figures.py",
        "scripts/paper/make_method_figures.py",
        "scripts/paper/make_moderate_tables.py",
        "scripts/paper/build_paper.sh",
    )
    offsets = [command.index(stage) for stage in stages]
    assert offsets == sorted(offsets)
    assert "--methods base standard heuristic bc_uniform pgrr" in command
    assert '--main-method "pgrr"' in command
    assert "scripts/paper/make_figures.py" not in command
    assert "scripts/paper/make_tables.py" not in command
