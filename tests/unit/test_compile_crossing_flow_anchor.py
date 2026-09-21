from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "student" / "compile_crossing_flow_anchor.py"
CONFIG = ROOT / "configs" / "experiments" / "pgrr_advantage_screen_crossing_v1.yaml"
CONFIG_V2 = ROOT / "configs" / "experiments" / "pgrr_advantage_screen_crossing_v2.yaml"
CONFIG_V2_R01 = (
    ROOT
    / "configs"
    / "experiments"
    / "pgrr_advantage_screen_crossing_v2_train_r01.yaml"
)
CONFIG_V2_R02 = (
    ROOT
    / "configs"
    / "experiments"
    / "pgrr_advantage_screen_crossing_v2_train_r02.yaml"
)
VALIDATION_CONFIGS = tuple(
    ROOT
    / "configs"
    / "experiments"
    / f"pgrr_advantage_screen_crossing_v2_validation_r0{replicate}.yaml"
    for replicate in range(3)
)


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("compile_crossing_flow_anchor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_anchor_is_train_only_one_shot_medium_crossing() -> None:
    module = _module()
    config = module.load_config(CONFIG)
    scenario = module.build_scenario(config)

    metadata = scenario["ramp_metadata"]
    assert metadata["benchmark_id"] == "pgrr_advantage_screen_v1"
    assert metadata["split"] == "train"
    assert metadata["held_out_test_materialized"] is False
    assert metadata["scenario_id"] == "crossing_flow_medium_anchor_v1_train_r00_s95010"
    assert len(scenario["obstacles"]["dynamic"]) == 2
    assert all(actor["cyclic_goals"] is False for actor in scenario["obstacles"]["dynamic"])
    assert all(actor["behavior"]["once"] is True for actor in scenario["obstacles"]["dynamic"])


def test_anchor_offline_gate_passes_and_writes_hash_bound_artifacts(tmp_path: Path) -> None:
    report = _module().compile_anchor(CONFIG, tmp_path)

    assert report["ready_for_single_seed_runtime_pair"] is True
    assert report["held_out_test_materialized"] is False
    assert report["temporal_conflict_count"] >= 1
    assert report["static_subgoal_count"] == 21
    assert all(report["checks"].values())
    scenario_path = Path(report["scenario_path"])
    preview_path = Path(report["preview_path"])
    assert scenario_path.is_file()
    assert preview_path.is_file()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["seed"] == 95010
    assert report["scenario_sha256"] == hashlib.sha256(scenario_path.read_bytes()).hexdigest()


def test_anchor_rejects_test_materialization(tmp_path: Path) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["split"]["name"] = "test"
    config["split"]["held_out_test_enabled"] = True
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(yaml.safe_dump(config), encoding="utf-8")

    try:
        _module().load_config(invalid)
    except ValueError as error:
        assert "train only" in str(error)
    else:
        raise AssertionError("test materialization must be rejected")


def test_v2_limits_route_and_preserves_post_conflict_rejoin_segment(
    tmp_path: Path,
) -> None:
    report = _module().compile_anchor(CONFIG_V2, tmp_path)

    assert report["scenario_id"] == "crossing_flow_medium_anchor_v2_train_r00_s95010"
    assert report["start_goal_distance_m"] == 15.0
    assert report["post_conflict_distance_m"] >= 5.0
    assert report["checks"]["start_goal_distance_within_limit"] is True
    assert report["checks"]["post_conflict_rejoin_segment_sufficient"] is True
    assert report["ready_for_single_seed_runtime_pair"] is True


def test_v2_train_replicates_change_only_declared_identity_fields() -> None:
    configs = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in (CONFIG_V2, CONFIG_V2_R01, CONFIG_V2_R02)
    ]

    def normalized(config: dict) -> dict:  # type: ignore[type-arg]
        value = json.loads(json.dumps(config))
        value["source_prior"]["note"] = "<replicate-note>"
        value["split"]["seed"] = "<seed>"
        value["split"]["replicate"] = "<replicate>"
        value["output"]["scenario_id"] = "<scenario-id>"
        return value

    assert normalized(configs[0]) == normalized(configs[1]) == normalized(configs[2])
    assert [config["split"]["seed"] for config in configs] == [95010, 95011, 95012]
    assert [config["split"]["replicate"] for config in configs] == [0, 1, 2]


def test_v2_validation_replicates_are_independent_and_geometry_frozen(
    tmp_path: Path,
) -> None:
    train = yaml.safe_load(CONFIG_V2.read_text(encoding="utf-8"))
    validation = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in VALIDATION_CONFIGS]

    def geometry(config: dict) -> dict:  # type: ignore[type-arg]
        return {
            key: config[key]
            for key in ("map", "robot", "family", "screening", "moderation")
        }

    assert all(geometry(config) == geometry(train) for config in validation)
    assert [config["split"]["seed"] for config in validation] == [96000, 96001, 96002]
    assert set(config["split"]["seed"] for config in validation).isdisjoint(
        {95010, 95011, 95012}
    )
    for index, path in enumerate(VALIDATION_CONFIGS):
        report = _module().compile_anchor(path, tmp_path / f"r{index:02d}")
        assert report["split"] == "validation"
        assert report["ready_for_single_seed_runtime_pair"] is True
        assert report["held_out_test_materialized"] is False
