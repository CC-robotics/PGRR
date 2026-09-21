from __future__ import annotations

import json
from pathlib import Path

from scripts.student.summarize_goal_approach_lateral_v2_screen import build_summary


def test_screen_summary_preserves_infra_attempt_and_promotes(tmp_path: Path) -> None:
    prefix = "pgrr_priority_goalapproach_v2_train_s97100"
    common = {"detail": "test", "physical_goal_distance_m": 0.2}
    outcomes = {
        f"{prefix}_base": {"outcome": "SIMULATOR_FAILURE", "sample_count": 0},
        f"{prefix}_base_retry01": {
            "outcome": "COLLISION",
            "sample_count": 2,
            "scenario_events": [{"transition": "pre_event_to_active_event"}],
        },
        f"{prefix}_pgrr": {
            "outcome": "GOAL_REACHED",
            "sample_count": 3,
            "scenario_events": [
                {"transition": "pre_event_to_active_event"},
                {"transition": "active_event_to_released"},
            ],
        },
    }
    for stem, values in outcomes.items():
        payload = {"episode_id": stem, **common, **values}
        (tmp_path / f"{stem}.outcome.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    rows = [
        {
            "timestamp": 0.0,
            "recovery_state": 2,
            "recovery_action": 22,
            "recovery_reason": "bc_onnx confidence=0.9",
            "goal": [20.0, 12.0],
        },
        {
            "timestamp": 1.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "original_goal_restored",
            "goal": [20.0, 12.0],
        },
        {
            "timestamp": 2.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "original_goal_restored",
            "goal": [20.0, 12.0],
        },
    ]
    (tmp_path / f"{prefix}_pgrr.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
    )

    summary = build_summary(tmp_path)

    assert summary["positive_pair"] is True
    assert summary["event_chain_complete_for_pgrr"] is True
    assert summary["eligible_for_train_replication"] is True
    assert summary["preserved_infrastructure_attempt"]["outcome"] == "SIMULATOR_FAILURE"
