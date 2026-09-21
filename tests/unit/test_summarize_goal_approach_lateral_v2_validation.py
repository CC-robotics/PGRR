from __future__ import annotations

from pathlib import Path

import pytest

from scripts.student.summarize_goal_approach_lateral_v2_validation import build_summary

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "outputs/student/goal_approach_lateral_v2_validation/runtime"


@pytest.mark.skipif(not RUNTIME.exists(), reason="runtime evidence not present")
def test_validation_gate_audits_all_three_pairs() -> None:
    summary = build_summary(RUNTIME)

    assert summary["qualifying_pair_count"] == 3
    assert summary["total_pair_count"] == 3
    assert summary["validation_gate_passed"] is True
    assert summary["retry_artifacts"] == []
    assert summary["frozen_test_used"] is False
    assert summary["general_superiority_claim_authorized"] is False

    for row in summary["selected_pairs"]:
        assert row["base"]["outcome"] == "COLLISION"
        assert row["base"]["detail"] == "privileged robot-human overlap"
        assert row["pgrr"]["outcome"] == "GOAL_REACHED"
        assert row["pgrr_event_chain_complete"] is True
        assert row["pgrr_original_goal_restored"] is True
        assert row["qualifying_pair"] is True
