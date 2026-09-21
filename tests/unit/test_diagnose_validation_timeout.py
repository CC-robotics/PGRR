import json
import math
from pathlib import Path

from scripts.student.diagnose_validation_timeout import diagnose


def _reason(path_post: str, final_post: str) -> str:
    return (
        "mask_stage=map_connectivity pre=0,21,22 post=0,21,22; "
        "mask_stage=observable_scan pre=0,21,22 post=0,21,22; "
        f"mask_stage=path_corridor pre=0,21,22 post={path_post}; "
        f"bc_directional_yield=active pre={path_post} post={final_post}; "
        "bc_onnx confidence=0.700"
    )


def test_diagnoses_progress_cycles_and_downstream_constraint(tmp_path: Path) -> None:
    rows = [
        {
            "timestamp": 0.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "",
            "distance_to_goal": 10.0,
            "robot_pose": [0.0, 0.0, 0.0],
        },
        {
            "timestamp": 1.0,
            "recovery_state": 2,
            "recovery_action": 22,
            "recovery_reason": _reason("0,21,22", "21,22"),
            "distance_to_goal": 9.0,
            "robot_pose": [1.0, 0.0, 0.0],
        },
        {
            "timestamp": 2.0,
            "recovery_state": 3,
            "recovery_action": 21,
            "recovery_reason": _reason("21,22", "21,22"),
            "distance_to_goal": 9.4,
            "robot_pose": [0.6, 0.0, 0.0],
        },
        {
            "timestamp": 3.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "original_goal_restored",
            "distance_to_goal": 9.2,
            "robot_pose": [0.8, 0.0, 0.0],
        },
    ]
    jsonl = tmp_path / "episode.jsonl"
    jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    outcome = tmp_path / "episode.outcome.json"
    outcome.write_text(
        json.dumps({"episode_id": "validation_smoke", "outcome": "TIMEOUT", "sample_count": 4}),
        encoding="utf-8",
    )

    report = diagnose(jsonl, outcome)

    assert math.isclose(report["goal_distance"]["progress_after_first_failure_m"], -0.2)
    assert report["cycle_summary"]["cycle_count"] == 1
    assert report["cycle_summary"]["nonpositive_progress_cycle_count"] == 1
    summary = report["trace_constraint_summary"]
    assert summary["path_stage_temporary_survivor_row_count"] == 1
    assert summary["path_survivors_removed_downstream_count"] == 1
    assert summary["path_survivors_retained_final_count"] == 0
    assert summary["path_survivor_action_counts"] == {"BACKUP": 1}
    assert summary["final_wait_backup_only_row_count"] == 2
    assert summary["temporary_subgoal_selected_count"] == 0


def test_rejects_sample_count_mismatch(tmp_path: Path) -> None:
    jsonl = tmp_path / "episode.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "timestamp": 0.0,
                "recovery_state": 1,
                "distance_to_goal": 1.0,
                "robot_pose": [0.0, 0.0, 0.0],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    outcome = tmp_path / "episode.outcome.json"
    outcome.write_text(json.dumps({"sample_count": 2}), encoding="utf-8")

    try:
        diagnose(jsonl, outcome)
    except ValueError as error:
        assert "sample count" in str(error)
    else:
        raise AssertionError("mismatched sample count must be rejected")
