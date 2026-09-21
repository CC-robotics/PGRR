from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/audit_raw_mask_replay_fields.py"
    spec = importlib.util.spec_from_file_location("audit_raw_mask_replay_fields", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_field_audit_distinguishes_exact_and_approximate_replay() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    rows = [
        {
            "recovery_action": 21,
            "recovery_reason": "bc_onnx confidence=0.9",
            "robot_pose": [1.0, 2.0, 0.0],
            "lidar": [6.0] * 180,
            "global_path": [[1.0, 2.0], [3.0, 2.0]],
        }
    ]

    result = module.assess_rows(rows)

    assert result["learned_decision_count"] == 1
    assert result["scan_layer_approximate_replay"]
    assert result["corridor_layer_approximate_replay"]
    assert not result["map_layer_exact_replay"]
    assert not result["scan_layer_exact_replay"]
    assert not result["corridor_layer_exact_replay"]


def test_no_learned_rows_do_not_count_as_complete() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])

    result = module.assess_rows([])

    assert result["learned_decision_count"] == 0
    assert not result["scan_layer_approximate_replay"]
    assert result["field_complete_counts"]["robot_pose_len3"] == 0
