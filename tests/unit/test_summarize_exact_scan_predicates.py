from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module(root: Path):
    path = root / "scripts/student/summarize_exact_scan_predicates.py"
    spec = importlib.util.spec_from_file_location("summarize_exact_scan_predicates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(after: str, directional: str, capsule: str) -> dict:
    return {
        "recovery_reason": (
            "mask_stage=observable_scan pre=0,1,2,21 post="
            f"{after}; mask_scan_predicates directional_pass={directional} "
            f"capsule_pass={capsule} target_clearance_m=0.900 swept_clearance_m=0.900"
        )
    }


def test_exact_intersection_is_verified() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    event = module.parse_event(_row("1,21", "0,1", "1,2"))
    assert event is not None
    assert event["expected_after"] == [1]
    assert event["exact_equivalence"]


def test_summary_distinguishes_capsule_only_failure() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    event = module.parse_event(_row("1,21", "0,1", "1,2"))
    summary = module.summarize([event])
    assert summary["all_equivalent"]
    assert summary["action_predicate_counts"] == {
        "capsule_only_failed": 1,
        "directional_only_failed": 1,
        "passed_both": 1,
    }


def test_partial_trace_is_rejected() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    with pytest.raises(ValueError, match="occur together"):
        module.parse_event(
            {"recovery_reason": "mask_stage=observable_scan pre=0,21 post=21"}
        )
