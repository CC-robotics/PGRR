from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module(root: Path):
    path = root / "scripts/student/summarize_capsule_failure_locations.py"
    spec = importlib.util.spec_from_file_location("summarize_capsule_failure_locations", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row() -> dict:
    minimums = ",".join(f"{index}:{0.2 + index / 100:.3f}" for index in range(21))
    fractions = ",".join(f"{index}:{index / 20:.3f}" for index in range(21))
    return {
        "recovery_action": 22,
        "recovery_reason": (
            "mask_stage=observable_scan pre="
            + ",".join(map(str, range(21)))
            + ",21 post=0,21; bc_yield_mask=active pre=0,21 post=21; "
            "mask_scan_predicates directional_pass=0,1 "
            "capsule_pass=0 target_clearance_m=0.900 swept_clearance_m=0.900 "
            "capsule_failures=segment_interior:1,2,3,4,5,6,7,8,9,10|"
            "segment_endpoint:11,12,13,14,15,16,17,18,19,20 "
            f"capsule_min_m={minimums} capsule_fraction={fractions}"
        )
    }


def test_parse_requires_complete_complement_and_distances() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    event = module.parse_event(_row())
    assert event is not None
    assert event["capsule_pass"] == [0]
    assert len(event["categories"]) == 20
    assert event["minimums_m"][0] == pytest.approx(0.2)


def test_summary_counts_failure_locations() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    event = module.parse_event(_row())
    summary = module.summarize([event])
    assert summary["category_action_counts"] == {
        "segment_endpoint": 10,
        "segment_interior": 10,
    }
    assert summary["empty_after_count"] == 0
    assert summary["nonempty_scan_selected_action_counts"] == {"22": 1}
    assert summary["nonempty_scan_selected_temporary_count"] == 0
    assert summary["scan_nonempty_final_temporary_empty_count"] == 1
    assert summary["scan_nonempty_final_temporary_nonempty_count"] == 0


def test_missing_location_trace_is_rejected() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    with pytest.raises(ValueError, match="occur together"):
        module.parse_event(
            {"recovery_reason": "mask_stage=observable_scan pre=0,21 post=21"}
        )
