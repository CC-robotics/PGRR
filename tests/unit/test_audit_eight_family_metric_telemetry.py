from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/audit_eight_family_metric_telemetry.py"
SPEC = importlib.util.spec_from_file_location("metric_telemetry_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _report() -> dict:
    matrix = json.loads(
        (ROOT / "outputs/student/paper_design/eight_family_method_metric_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    return MODULE.build_audit(matrix)


def test_all_matrix_metrics_are_classified() -> None:
    report = _report()
    assert report["metric_count"] == 20
    assert sum(report["status_counts"].values()) == 20


def test_only_clearance_and_deadlock_need_definitions() -> None:
    report = _report()
    assert report["blocking_definition_decisions"] == [
        "deadlock_duration_s",
        "minimum_clearance_m",
    ]


def test_core_outcomes_and_costs_have_sources() -> None:
    rows = {row["metric"]: row for row in _report()["metrics"]}
    for metric in (
        "GOAL_REACHED",
        "COLLISION",
        "TIMEOUT",
        "completion_time_s",
        "path_length_m",
        "angular_jerk",
    ):
        assert rows[metric]["status"] in {"direct", "derivable"}
        assert rows[metric]["source_fields"]
