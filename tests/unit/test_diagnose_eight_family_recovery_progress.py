from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/diagnose_eight_family_recovery_progress.py"
    spec = importlib.util.spec_from_file_location("diagnose_recovery_progress", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnose_episode_tracks_original_goal_and_recovery_cycles(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    rows = [
        {
            "timestamp": 0.0,
            "robot_pose": [0.0, 0.0, 0.0],
            "robot_velocity": [0.2, 0.0],
            "goal": [10.0, 0.0, 0.0],
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "not_triggered",
            "failure_prediction": [0.0, 0.0, 0.0, 0.0],
        },
        {
            "timestamp": 1.0,
            "robot_pose": [1.0, 0.0, 0.0],
            "robot_velocity": [0.0, 0.0],
            "goal": [2.0, 1.0, 0.0],
            "recovery_state": 2,
            "recovery_action": 22,
            "recovery_reason": "emergency_backup",
            "failure_prediction": [0.0, 1.0, 0.0, 0.0],
        },
        {
            "timestamp": 2.0,
            "robot_pose": [2.0, 0.0, 0.0],
            "robot_velocity": [0.2, 0.0],
            "goal": [10.0, 0.0, 0.0],
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "original_goal_restored",
            "failure_prediction": [0.0, 0.0, 0.0, 0.0],
        },
    ]
    path = tmp_path / "episode.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    result = module.diagnose_episode(path, digest)

    assert result["net_original_goal_progress_m"] == 2.0
    assert result["path_length_m"] == 2.0
    assert result["recovery_cycle_count"] == 1
    assert result["completed_rejoin_count"] == 1
    assert result["positive_progress_cycle_count"] == 1
    assert result["recovery_time_fraction"] == 0.5
    assert result["low_linear_speed_sample_fraction"] == 0.5
    assert result["recovery_cycles"][0]["dominant_failure_at_trigger"] == "FREEZE"
    assert result["recovery_cycles"][0]["action_signature"] == "BACKUP>CONTINUE"
    assert result["recovery_cycles"][0]["learned_decision_count"] == 0
