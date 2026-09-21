from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.student.summarize_goal_approach_lateral_v2_replication import (
    build_summary,
)

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "outputs/student/goal_approach_lateral_v2_screen/runtime"
REPLICATION = ROOT / "outputs/student/goal_approach_lateral_v2_replication/runtime"


@pytest.mark.skipif(not REPLICATION.exists(), reason="runtime evidence not present")
def test_train_replication_gate_uses_all_predeclared_pairs() -> None:
    summary = build_summary(SCREEN, REPLICATION)

    assert summary["qualifying_pair_count"] == 3
    assert summary["total_pair_count"] == 3
    assert summary["train_replication_gate_passed"] is True
    assert summary["independent_validation_complete"] is False
    assert summary["paper_claim_authorized"] is False
    assert len(summary["preserved_infrastructure_attempts"]) == 1

    for row in summary["selected_pairs"]:
        assert row["base"]["outcome"] == "COLLISION"
        assert row["base"]["detail"] == "privileged robot-human overlap"
        assert row["pgrr"]["outcome"] == "GOAL_REACHED"
        assert row["positive_pair"] is True
        assert row["pgrr_event_chain_complete"] is True
        assert row["pgrr_original_goal_restored"] is True


@pytest.mark.skipif(not REPLICATION.exists(), reason="runtime evidence not present")
def test_runtime_outcomes_are_valid_json() -> None:
    for path in REPLICATION.glob("*.outcome.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["episode_id"]
        assert value["outcome"] in {
            "GOAL_REACHED",
            "COLLISION",
            "TIMEOUT",
            "PLANNER_FAILURE",
            "SIMULATOR_FAILURE",
            "INVALID_RESET",
        }
