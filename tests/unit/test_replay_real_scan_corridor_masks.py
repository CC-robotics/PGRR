from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/replay_real_scan_corridor_masks.py"
    spec = importlib.util.spec_from_file_location("replay_real_scan_corridor_masks", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(lidar_range: float, pre: str) -> dict:
    return {
        "robot_pose": [2.0, 0.0, 0.0],
        "lidar": [lidar_range] * 180,
        "global_path": [[0.0, 0.0], [10.0, 0.0]],
        "failure_prediction": [0.0, 0.0, 0.0, 0.0],
        "recovery_reason": f"bc_yield_mask=active pre={pre} post={pre}",
    }


def test_replay_explains_empty_mask_under_close_scan() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])

    result = module.replay_row(_row(0.30, "21,22"))

    assert result is not None
    assert result["logged_subgoal_count"] == 0
    assert result["replayed_subgoal_count"] == 0
    assert result["logged_empty_explained"]


def test_replay_reports_approximation_disagreement() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])

    result = module.replay_row(_row(8.0, "0,21,22"))

    assert result is not None
    assert result["logged_subgoal_ids"] == [0]
    assert result["replayed_subgoal_count"] == 11
    assert result["replay_not_in_logged"]
    assert result["logged_is_subset_of_replay"]
