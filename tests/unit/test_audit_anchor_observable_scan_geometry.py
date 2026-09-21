from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/audit_anchor_observable_scan_geometry.py"
    spec = importlib.util.spec_from_file_location("audit_anchor_observable_scan_geometry", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(scan: float, post: str, risk: float = 0.0) -> dict:
    return {
        "lidar": [scan] * 180,
        "failure_prediction": [risk, 0.0, 0.0, 0.0],
        "recovery_reason": (
            "forward_clearance_m=4.000; "
            "mask_stage=map_connectivity pre=0,1,21 post=0,1,21; "
            f"mask_stage=observable_scan pre=0,1,21 post={post}; "
            f"mask_stage=path_corridor pre={post} post={post}"
        ),
    }


def test_open_scan_replays_retained_subgoals() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    result = module.analyze_row(_row(8.0, "0,1,21"))
    assert result is not None
    assert result["retained"] == [0, 1]
    assert result["approximate_retained"] == [0, 1]
    assert result["approximate_exact_match"]


def test_close_scan_replays_empty_subgoals() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    result = module.analyze_row(_row(0.3, "21"))
    assert result is not None
    assert result["retained"] == []
    assert result["approximate_retained"] == []
    assert result["approximate_exact_match"]


def test_summary_keeps_exact_and_approximate_counts_separate() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    events = [module.analyze_row(_row(8.0, "21", risk=0.75))]
    summary = module._summarize_events([event for event in events if event is not None])
    assert summary["decision_count"] == 1
    assert summary["all_temporary_empty_count"] == 1
    assert summary["all_empty_with_forward_clearance_at_least_1_5m_count"] == 1
    assert summary["approximate_exact_decision_match_count"] == 0
    assert summary["exact_logged_latch_empty_counts"] == {
        "latched:decisions": 1,
        "latched:empty": 1,
    }
    assert summary["exact_logged_radius_counts"]["0.6m"]["considered"] == 2
