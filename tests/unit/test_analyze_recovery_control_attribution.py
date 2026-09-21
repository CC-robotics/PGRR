from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/analyze_recovery_control_attribution.py"
    spec = importlib.util.spec_from_file_location("analyze_control_attribution", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_final_post_mask_uses_last_constraint() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])

    assert module.parse_final_post_mask("pre=0,21,22 post=21,22; post=21") == (21,)
    assert module.parse_final_post_mask("bc_onnx confidence=1.0") is None
    assert module.parse_final_post_mask("pre=21 post=none; bc_onnx") == ()


def test_analyze_episode_separates_mask_policy_and_emergency_guard() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    rows = [
        {
            "timestamp": 0.0,
            "recovery_action": 21,
            "recovery_reason": "mask pre=0,21,22 post=0,21,22; bc_onnx confidence=0.9",
        },
        {
            "timestamp": 0.1,
            "recovery_action": 21,
            "recovery_reason": "emergency_stop",
        },
        {
            "timestamp": 0.2,
            "recovery_action": 22,
            "recovery_reason": "mask pre=21,22 post=21,22; bc_onnx confidence=0.8",
        },
    ]

    events = module.analyze_episode(rows)

    assert len(events) == 2
    assert events[0]["alternative_action_available"]
    assert events[0]["selected_wait_or_backup"]
    assert events[0]["immediately_followed_by_emergency_guard"]
    assert events[1]["only_wait_backup_allowed"]
    assert events[1]["selected_action_in_logged_mask"]
