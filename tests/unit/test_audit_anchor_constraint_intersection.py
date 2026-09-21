from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/audit_anchor_constraint_intersection.py"
    spec = importlib.util.spec_from_file_location("audit_anchor_constraint_intersection", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_survivor_is_attributed_to_yield_constraint() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    row = {
        "recovery_action": 22,
        "recovery_reason": (
            "mask_stage=observable_scan pre=0,1,2,21 post=2,21; "
            "mask_stage=path_corridor pre=2,21 post=2,21; "
            "bc_yield_mask=active pre=2,21 post=21; bc_onnx confidence=0.8"
        ),
    }
    event = module.parse_event(row)
    assert event is not None
    assert event["first_empty_constraint"] == "bc_yield_mask"
    assert event["final_temporary"] == []
    summary = module.summarize([event])
    assert summary["scan_survivor_action_occurrences"] == {"2": 1}
    assert summary["removed_action_occurrences_by_downstream_constraint"] == {
        "bc_yield_mask": {"2": 1}
    }
    assert summary["scan_survivor_geometry"]["2"] == {
        "action_id": 2,
        "radius_m": 0.6,
        "angle_deg": -30,
    }


def test_scan_empty_is_not_misattributed_downstream() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    row = {
        "recovery_action": 21,
        "recovery_reason": (
            "mask_stage=observable_scan pre=0,1,21 post=21; "
            "mask_stage=path_corridor pre=21 post=21; bc_onnx confidence=0.5"
        ),
    }
    event = module.parse_event(row)
    assert event is not None
    assert event["first_empty_constraint"] == "observable_scan"
    assert module.summarize([event])["scan_empty_count"] == 1


def test_non_trace_row_is_ignored() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    assert module.parse_event({"recovery_reason": "bc_onnx confidence=0.5"}) is None
