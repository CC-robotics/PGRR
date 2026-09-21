from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.student.compile_closing_gap_bounded_v2 import (
    DEFAULT_CONFIG,
    compile_candidate,
)


def test_bounded_closing_gap_v2_passes_offline_gate(tmp_path: Path) -> None:
    report = compile_candidate(DEFAULT_CONFIG, tmp_path)

    assert report["ready_for_single_seed_runtime_pair"] is True
    assert report["route_distance_m"] == 15.0
    assert report["post_conflict_distance_m"] == 5.0
    assert 2.0 <= report["active_duration_s"] <= 4.0
    assert report["static_subgoal_count"] == 21
    assert all(report["checks"].values())

    scenario = json.loads(Path(report["scenario_path"]).read_text(encoding="utf-8"))
    assert report["scenario_sha256"] == hashlib.sha256(
        Path(report["scenario_path"]).read_bytes()
    ).hexdigest()
    assert scenario["obstacles"]["static"] == []
    assert len(scenario["obstacles"]["dynamic"]) == 2
    assert len(scenario["ramp_event_control"]["events"]) == 2
    assert all(
        event["trigger_metric"] == "robot_goal_distance_below"
        for event in scenario["ramp_event_control"]["events"]
    )
    assert all(
        event["commands"]["released"] == "resume_noncyclic_route"
        for event in scenario["ramp_event_control"]["events"]
    )


def test_v3_changes_only_terminal_clearance_identity_and_event_label(
    tmp_path: Path,
) -> None:
    v2 = json.loads(
        Path(compile_candidate(DEFAULT_CONFIG, tmp_path / "v2")["scenario_path"])
        .read_text(encoding="utf-8")
    )
    v3_config = DEFAULT_CONFIG.with_name("pgrr_closing_gap_bounded_v3_train_r00.yaml")
    v3_report = compile_candidate(v3_config, tmp_path / "v3")
    v3 = json.loads(Path(v3_report["scenario_path"]).read_text(encoding="utf-8"))

    assert v3_report["ready_for_single_seed_runtime_pair"] is True
    assert v3_report["terminal_route_clearance_m"] == [3.5, 3.5]
    assert v2["robots"] == v3["robots"]
    assert [actor["pos"] for actor in v2["obstacles"]["dynamic"]] == [
        actor["pos"] for actor in v3["obstacles"]["dynamic"]
    ]
    assert [actor["max_vel"] for actor in v2["obstacles"]["dynamic"]] == [
        actor["max_vel"] for actor in v3["obstacles"]["dynamic"]
    ]
    assert all("_v3_train" in event["event_id"] for event in v3["ramp_event_control"]["events"])


def test_v3_train_replicates_change_only_identity_fields(tmp_path: Path) -> None:
    configs = [
        DEFAULT_CONFIG.with_name(f"pgrr_closing_gap_bounded_v3_train_r0{i}.yaml")
        for i in range(3)
    ]
    scenarios = []
    for i, config in enumerate(configs):
        report = compile_candidate(config, tmp_path / f"r{i:02d}")
        assert report["ready_for_single_seed_runtime_pair"] is True
        scenarios.append(
            json.loads(Path(report["scenario_path"]).read_text(encoding="utf-8"))
        )

    reference = scenarios[0]
    for replicate, scenario in enumerate(scenarios):
        assert scenario["robots"] == reference["robots"]
        assert scenario["obstacles"] == reference["obstacles"]
        assert scenario["ramp_event_control"] == reference["ramp_event_control"]
        assert scenario["ramp_metadata"]["replicate"] == replicate
        assert scenario["ramp_metadata"]["seed"] == 98200 + replicate
        assert scenario["ramp_metadata"]["split"] == "train"
        assert scenario["ramp_metadata"]["held_out_test_materialized"] is False
