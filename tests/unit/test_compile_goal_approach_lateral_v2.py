from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.student.compile_goal_approach_lateral_v2 import (
    DEFAULT_CONFIG,
    compile_candidate,
)


def test_goal_approach_v2_passes_bounded_one_shot_gate(tmp_path: Path) -> None:
    report = compile_candidate(DEFAULT_CONFIG, tmp_path)

    assert report["ready_for_single_seed_runtime_pair"] is True
    assert report["route_distance_m"] == 15.0
    assert report["post_conflict_distance_m"] == 5.0
    assert 37.0 <= report["nominal_interaction_time_s"] <= 58.0
    assert report["static_subgoal_count"] == 21
    assert all(report["checks"].values())

    scenario = json.loads(Path(report["scenario_path"]).read_text(encoding="utf-8"))
    actor = scenario["obstacles"]["dynamic"][0]
    assert actor["cyclic_goals"] is False
    assert scenario["obstacles"]["static"] == []
    event = scenario["ramp_event_control"]["events"][0]
    assert event["commands"]["pre_event"] == "hold_at_start"
    assert event["commands"]["released"] == "hold_at_off_path_terminal_waypoint"


def test_train_replicates_change_only_identity_fields() -> None:
    paths = [
        DEFAULT_CONFIG,
        DEFAULT_CONFIG.with_name("pgrr_goal_approach_lateral_v2_train_r01.yaml"),
        DEFAULT_CONFIG.with_name("pgrr_goal_approach_lateral_v2_train_r02.yaml"),
    ]
    configs = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]

    def normalized(config: dict) -> dict:  # type: ignore[type-arg]
        value = json.loads(json.dumps(config))
        value["split"]["seed"] = "<seed>"
        value["split"]["replicate"] = "<replicate>"
        value["output"]["scenario_id"] = "<scenario-id>"
        return value

    assert normalized(configs[0]) == normalized(configs[1]) == normalized(configs[2])
    assert [config["split"]["seed"] for config in configs] == [97100, 97101, 97102]


def test_validation_replicates_keep_frozen_behavior(tmp_path: Path) -> None:
    validation_paths = [
        DEFAULT_CONFIG.with_name(
            f"pgrr_goal_approach_lateral_v2_validation_r0{index}.yaml"
        )
        for index in range(3)
    ]
    train = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))

    def behavioral(config: dict) -> dict:  # type: ignore[type-arg]
        value = json.loads(json.dumps(config))
        value.pop("status")
        value.pop("split")
        value.pop("output")
        return value

    reports = [
        compile_candidate(path, tmp_path / f"validation_{index}")
        for index, path in enumerate(validation_paths)
    ]
    configs = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in validation_paths]

    assert all(behavioral(config) == behavioral(train) for config in configs)
    assert [config["split"]["seed"] for config in configs] == [98100, 98101, 98102]
    assert all(report["split"] == "validation" for report in reports)
    assert all(report["ready_for_single_seed_runtime_pair"] is True for report in reports)
