from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/audit_runtime_mask_pipeline.py"
    spec = importlib.util.spec_from_file_location("audit_runtime_mask_pipeline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_mask_pipeline_order_and_telemetry_gaps() -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    report = module.audit_source(
        root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
    )

    assert report["stage_count"] == 18
    calls = [stage["call"] for stage in report["stages"]]
    assert calls.index("compute_action_mask") < calls.index("apply_observable_scan_mask")
    assert calls.index("constrain_stalled_wait") < calls.index(
        "self._constrain_bc_recurrent_escape"
    )
    assert report["telemetry_gaps"]["upstream_before_yield"][-1] == (
        "constrain_rejoin_actions"
    )
    assert report["claim_boundary"] == "static_call_order_not_runtime_causality"
