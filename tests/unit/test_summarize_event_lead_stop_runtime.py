from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/summarize_event_lead_stop_runtime.py"


def _module():
    spec = importlib.util.spec_from_file_location("summarize_event_runtime", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_invalid_pgrr_pair_is_not_promoted(tmp_path: Path) -> None:
    base = {
        "outcome": "TIMEOUT",
        "sample_count": 10,
        "physical_goal_distance_m": 0.9,
        "scenario_events": [
            {"transition": "pre_event_to_active_event", "sim_time_s": 10.0},
            {"transition": "active_event_to_released", "sim_time_s": 13.0},
        ],
    }
    pgrr = {
        "outcome": "SIMULATOR_FAILURE",
        "detail": "logger stopped without terminal event",
        "sample_count": 2,
        "physical_goal_distance_m": 18.0,
        "scenario_events": [],
    }
    (tmp_path / "pgrr_event_leadstop_s92500_base.outcome.json").write_text(
        json.dumps(base), encoding="utf-8"
    )
    (tmp_path / "pgrr_event_leadstop_s92500_pgrr.outcome.json").write_text(
        json.dumps(pgrr), encoding="utf-8"
    )
    (tmp_path / "pgrr_event_leadstop_s92500_base_runtime.log").write_text(
        "base", encoding="utf-8"
    )
    (tmp_path / "pgrr_event_leadstop_s92500_pgrr_runtime.log").write_text(
        "pgrr", encoding="utf-8"
    )
    (tmp_path / "pgrr_event_leadstop_s92500_pgrr_retry01_runtime.log").write_text(
        "timed out waiting for required baseline topics", encoding="utf-8"
    )
    report = _module().summarize(tmp_path, tmp_path / "report.json")
    assert report["event_runtime_semantics_observed_on_base"] is True
    assert report["pgrr_retry_1"]["startup_topic_timeout"] is True
    assert report["paired_method_claim_authorized"] is False
    assert report["core_case_promotion_authorized"] is False
