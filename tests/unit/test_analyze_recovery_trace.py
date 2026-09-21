import json
from pathlib import Path

from scripts.student.analyze_recovery_trace import summarize_recovery


def test_summarize_recovery_counts_decision_events(tmp_path: Path) -> None:
    path = tmp_path / "episode.jsonl"
    rows = [
        {
            "timestamp": timestamp,
            "goal": [5.0, 6.0, 0.0],
            "recovery_state": state,
            "recovery_action": action,
            "recovery_reason": reason,
        }
        for timestamp, state, action, reason in [
            (0.0, 0, 24, "not_triggered"),
            (1.0, 2, 0, "bc_onnx confidence=0.9 latency_ms=0.2"),
            (2.0, 2, 0, "bc_onnx confidence=0.9 latency_ms=0.2"),
            (3.0, 3, 24, "recovery_action_complete"),
            (4.0, 0, 24, "original_goal_restored"),
        ]
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    summary = summarize_recovery(path)

    assert summary["decision_event_count"] == 4
    assert summary["temporary_subgoal_decision_count"] == 1
    assert summary["original_goal_restored_event_count"] == 1
    assert summary["distinct_logged_task_goals"] == 1
    assert [item["recovery_state"] for item in summary["state_transitions"]] == [0, 2, 3, 0]
