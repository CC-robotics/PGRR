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
