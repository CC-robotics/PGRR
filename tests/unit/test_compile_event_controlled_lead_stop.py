from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/compile_event_controlled_lead_stop.py"


def _module():
    spec = importlib.util.spec_from_file_location("compile_event_lead_stop", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compile_train_only_bounded_lead_stop(tmp_path: Path) -> None:
    report = _module().compile_candidate(
        ROOT / "configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml",
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml",
        tmp_path,
    )
    assert report["split"] == "train"
    assert report["candidate_id"] == "lead_stop_bounded_release_v2_train_r00_s92500"
    assert report["held_out_test_materialized"] is False
    assert report["paired_methods_share_one_scenario"] is True
    assert report["event_mapping_valid"] is True
    assert report["actor_route_noncyclic"] is True
    assert report["actor_terminal_route_clearance_m"] >= 1.0
    assert report["initial_trigger_metric_m"] > report["trigger_arm_threshold_m"]
    assert report["initial_trigger_metric_m"] == 3.75
    assert report["runtime_executed"] is False
    scenario_path = Path(report["scenario_path"])
    if not scenario_path.is_absolute():
        scenario_path = ROOT / scenario_path
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["split"] == "train"
    assert scenario["ramp_metadata"]["paired_methods"] == ["base", "pgrr"]
    assert scenario["obstacles"]["dynamic"][0]["cyclic_goals"] is False
    event = scenario["ramp_event_control"]["events"][0]
    assert event["commands"] == {
        "pre_event": "advance_route",
        "active_event": "hold_actor_route_clock",
        "released": "resume_noncyclic_route",
    }


def test_compiler_contains_no_test_materialization_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"split": "train"' in source
    assert "choices=(\"train\", \"validation\", \"test\")" not in source
    assert "moderate_v6" not in source
