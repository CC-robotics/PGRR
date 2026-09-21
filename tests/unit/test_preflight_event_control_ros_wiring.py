from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = ROOT / "scripts/student/preflight_event_control_ros_wiring.py"
    spec = importlib.util.spec_from_file_location("event_ros_preflight", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_tree_has_prerequisites_and_default_off_runtime_wiring() -> None:
    report = _module().inspect(ROOT)
    assert report["existing_prerequisite_count"] == report["existing_prerequisite_total"]
    assert report["runtime_wiring_present_count"] == report["runtime_wiring_total"]
    assert report["ready_for_event_scenario_execution"] is True
    assert report["default_behavior_changed"] is False
    assert len(report["required_changes"]) == 7


def test_preflight_hashes_every_source_boundary() -> None:
    report = _module().inspect(ROOT)
    assert set(report["source_hashes"]) == set(_module().SOURCE_PATHS)
    assert all(len(item["sha256"]) == 64 for item in report["source_hashes"].values())


def test_acceptance_requires_policy_isolation_and_stale_pose_failure() -> None:
    acceptance = _module().inspect(ROOT)["acceptance_after_wiring"]
    assert any("absent from recovery observation" in item for item in acceptance)
    assert any("stale simulator pose" in item for item in acceptance)
