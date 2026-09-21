from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/compile_event_controlled_closing_gap.py"


def _module():
    spec = importlib.util.spec_from_file_location("compile_closing_gap_event", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_closing_gap_is_train_only_and_dynamic(tmp_path: Path) -> None:
    report = _module().compile_candidate(tmp_path)
    assert report["candidate_id"] == "closing_gap_open_release_v1_train_r00_s91410"
    assert report["split"] == "train"
    assert report["held_out_test_materialized"] is False
    assert report["paired_methods_share_one_scenario"] is True
    assert report["event_mapping_valid"] is True
    assert report["actor_count"] == 2
    assert report["actor_routes_noncyclic"] is True
    assert report["static_obstacle_count"] == 0
    path = Path(report["scenario_path"])
    if not path.is_absolute():
        path = ROOT / path
    scenario = json.loads(path.read_text(encoding="utf-8"))
    assert scenario["obstacles"]["static"] == []
    assert len(scenario["ramp_event_control"]["events"]) == 2
    for event in scenario["ramp_event_control"]["events"]:
        assert event["commands"]["pre_event"] == "hold_at_start"
        assert event["commands"]["active_event"] == (
            "release_actor_on_noncyclic_crossing"
        )


def test_compiler_has_no_test_split_or_moderate_v6() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"split": "train"' in source
    assert "moderate_v6" not in source
