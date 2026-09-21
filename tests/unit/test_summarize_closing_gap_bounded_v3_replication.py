from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.student.summarize_closing_gap_bounded_v3_replication import build_summary

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "outputs/student/closing_gap_bounded_v3_screen/runtime"
REPLICATION = ROOT / "outputs/student/closing_gap_bounded_v3_replication/runtime"


@pytest.mark.skipif(not REPLICATION.exists(), reason="runtime evidence not present")
def test_train_replication_gate_uses_all_predeclared_pairs() -> None:
    summary = build_summary(SCREEN, REPLICATION)

    assert summary["total_pair_count"] == 3
    assert summary["promotion_rule"]["minimum_qualifying_pairs"] == 2
    assert summary["independent_validation_complete"] is False
    assert summary["paper_claim_authorized"] is False
    for row in summary["selected_pairs"]:
        assert row["base"]["sample_count"] > 0
        assert row["pgrr"]["sample_count"] > 0


@pytest.mark.skipif(not REPLICATION.exists(), reason="runtime evidence not present")
def test_runtime_outcomes_use_preserved_vocabulary() -> None:
    allowed = {
        "GOAL_REACHED",
        "COLLISION",
        "TIMEOUT",
        "PLANNER_FAILURE",
        "SIMULATOR_FAILURE",
        "INVALID_RESET",
    }
    for path in REPLICATION.glob("*.outcome.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["episode_id"]
        assert value["outcome"] in allowed
