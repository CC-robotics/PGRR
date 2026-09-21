from __future__ import annotations

from pathlib import Path

import pytest

from scripts.student.summarize_closing_gap_bounded_v3_screen import build_summary

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "outputs/student/closing_gap_bounded_v2_screen/runtime"
V3 = ROOT / "outputs/student/closing_gap_bounded_v3_screen/runtime"


@pytest.mark.skipif(not V3.exists(), reason="runtime evidence not present")
def test_v3_screen_is_positive_and_auditable() -> None:
    summary = build_summary(V2, V3)

    assert summary["v2_diagnostic"]["pgrr_outcome"] == "TIMEOUT"
    assert summary["base"]["outcome"] == "COLLISION"
    assert summary["base"]["detail"] == "privileged robot-human overlap"
    assert summary["pgrr"]["outcome"] == "GOAL_REACHED"
    assert summary["positive_pair"] is True
    assert summary["pgrr_event_chain_complete_for_both_actors"] is True
    assert summary["pgrr_original_goal_restored"] is True
    assert summary["eligible_for_train_replication"] is True
    assert summary["paper_claim_authorized"] is False
