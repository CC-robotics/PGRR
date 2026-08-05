from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate.yaml"
V2_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate_v2.yaml"
V3_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate_v3.yaml"
V4_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate_v4.yaml"
V5_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate_v5.yaml"
SCRIPT = ROOT / "scripts" / "data" / "compile_moderate_benchmark.py"
FAMILIES = {
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
}


def _compiler():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("pgrr_moderate_compiler", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(root: Path, split: str, suffix: str = "moderate") -> dict:
    return yaml.safe_load((root / "splits" / f"{suffix}_{split}.yaml").read_text())


@pytest.fixture(scope="module")
def v3_compilation(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Any, Path, dict[str, Any]]:
    compiler = _compiler()
    output = tmp_path_factory.mktemp("moderate_v3")
    summary = compiler.compile_benchmark(
        V3_CONFIG,
        output,
        train_repetitions=1,
        validation_repetitions=1,
        test_repetitions=1,
        render_previews=False,
    )
    return compiler, output, summary


@pytest.fixture(scope="module")
def v4_compilation(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Any, Path, dict[str, Any]]:
    compiler = _compiler()
    output = tmp_path_factory.mktemp("moderate_v4")
    summary = compiler.compile_benchmark(
        V4_CONFIG,
        output,
        train_repetitions=1,
        validation_repetitions=1,
        test_repetitions=1,
        render_previews=False,
    )
    return compiler, output, summary


@pytest.fixture(scope="module")
def v5_compilation(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Any, Path, dict[str, Any]]:
    compiler = _compiler()
    output = tmp_path_factory.mktemp("moderate_v5")
    summary = compiler.compile_benchmark(
        V5_CONFIG,
        output,
        train_repetitions=1,
        validation_repetitions=1,
        test_repetitions=1,
        render_previews=False,
    )
    return compiler, output, summary


def test_moderate_catalog_has_declared_scale_and_disjoint_seed_blocks() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["densities"] == {"low": 1, "medium": 2, "high": 4}
    assert [family["id"] for family in config["families"]] == [
        "head_on_corridor",
        "doorway_bottleneck",
        "crossing_flow",
        "blind_corner",
        "group_blocking",
        "overtaking",
        "opposite_streams",
        "temporary_blockage",
    ]
    assert config["splits"]["validation"]["seed_base"] == 51000
    assert config["splits"]["validation"]["repetitions"] == 3
    assert config["splits"]["test"]["seed_base"] == 61000
    assert config["splits"]["test"]["repetitions"] == 5
    assert 2.4 <= config["moderation"]["corridor_footprint_clear_width_m"] <= 2.8
    assert 2.1 <= config["moderation"]["doorway_footprint_clear_width_m"] <= 2.5
    assert config["moderation"]["lane_offset_range_m"] == [0.65, 0.90]
    assert config["moderation"]["pedestrian_longitudinal_stagger_m"] == 1.50
    assert config["moderation"]["robot_avoidance_distance_m"] == 1.50
    assert 8 * 3 * config["splits"]["validation"]["repetitions"] == 72
    assert 8 * 3 * config["splits"]["test"]["repetitions"] == 120


def test_v2_catalog_preserves_scale_and_declares_recoverable_egress() -> None:
    config = yaml.safe_load(V2_CONFIG.read_text(encoding="utf-8"))
    assert config["benchmark_id"] == "moderate_social_navigation_v2"
    assert config["moderation"]["robot_avoidance_distance_m"] == 0.90
    assert config["moderation"]["head_on_exit_x_m"] == 3.00
    assert config["moderation"]["doorway_exit_x_m"] == 5.00
    assert config["output"] == {
        "generated_subdirectory": "moderate_v2/arena",
        "preview_subdirectory": "moderate_v2",
        "manifest_suffix": "moderate_v2",
    }
    assert config["densities"] == {"low": 1, "medium": 2, "high": 4}
    assert config["splits"]["validation"]["repetitions"] == 3
    assert config["splits"]["test"]["repetitions"] == 5


def test_v3_catalog_declares_recoverable_actor_dynamics_and_split_blocks() -> None:
    config = yaml.safe_load(V3_CONFIG.read_text(encoding="utf-8"))
    moderation = config["moderation"]
    assert config["benchmark_id"] == "moderate_social_navigation_v3"
    assert moderation["robot_avoidance_distance_m"] == 0.90
    assert moderation["robot_soft_yield_distance_m"] == 0.90
    assert moderation["robot_hard_guard_distance_m"] == 0.73
    assert moderation["actor_update_frequency_hz"] == 5.0
    assert moderation["actor_dynamics_version"] == "deterministic_one_shot_swept_guard_v1"
    assert moderation["doorway_single_side_lane_stream"] is True
    assert moderation["doorway_lane_offset_m"] == 0.75
    assert moderation["doorway_exit_x_m"] == 5.0
    assert config["output"]["manifest_suffix"] == "moderate_v3"
    assert {split: values["seed_base"] for split, values in config["splits"].items()} == {
        "train": 70000,
        "validation": 71000,
        "test": 81000,
    }


def test_v4_catalog_declares_single_side_head_on_stream_and_new_split_blocks() -> None:
    v3 = yaml.safe_load(V3_CONFIG.read_text(encoding="utf-8"))
    config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    moderation = config["moderation"]
    assert config["benchmark_id"] == "moderate_social_navigation_v4"
    assert moderation["head_on_single_side_lane_stream"] is True
    assert moderation["head_on_lane_offset_m"] == 0.75
    assert moderation["pedestrian_longitudinal_stagger_m"] == 1.50
    assert config["densities"] == {"low": 1, "medium": 2, "high": 4}
    assert config["families"] == v3["families"]
    assert config["output"] == {
        "generated_subdirectory": "moderate_v4/arena",
        "preview_subdirectory": "moderate_v4",
        "manifest_suffix": "moderate_v4",
    }
    assert {split: values["seed_base"] for split, values in config["splits"].items()} == {
        "train": 72000,
        "validation": 73000,
        "test": 83000,
    }
    assert {split: values["repetitions"] for split, values in config["splits"].items()} == {
        "train": 3,
        "validation": 3,
        "test": 5,
    }


def test_v5_catalog_is_validation_calibrated_and_uses_fresh_split_blocks() -> None:
    config = yaml.safe_load(V5_CONFIG.read_text(encoding="utf-8"))
    moderation = config["moderation"]
    assert config["benchmark_id"] == "moderate_social_navigation_v5"
    assert moderation["blind_corner_vertical_end_y_m"] == 10.80
    assert moderation["blind_corner_horizontal_start_x_m"] == 15.50
    assert moderation["group_nearest_actor_offset_m"] == 1.15
    assert moderation["overtaking_lane_offset_range_m"] == [0.96, 1.16]
    assert moderation["opposite_stream_lane_offset_range_m"] == [0.96, 1.16]
    assert moderation["temporary_doorway_center_half_gap_m"] == 2.20
    assert moderation["temporary_crossing_half_span_m"] == 1.00
    assert moderation["temporary_crossing_x_spacing_m"] == 0.80
    assert moderation["temporary_crossing_lead_in_m"] == 1.40
    assert moderation["validate_actor_static_clearance"] is True
    assert config["output"] == {
        "generated_subdirectory": "moderate_v5/arena",
        "preview_subdirectory": "moderate_v5",
        "manifest_suffix": "moderate_v5",
    }
    assert {split: values["seed_base"] for split, values in config["splits"].items()} == {
        "train": 74000,
        "validation": 75000,
        "test": 85000,
    }
    assert {split: values["repetitions"] for split, values in config["splits"].items()} == {
        "train": 3,
        "validation": 3,
        "test": 5,
    }


def test_route_parameter_defaults_preserve_v1_endpoints() -> None:
    compiler = _compiler()
    head_routes = compiler._moderate_routes(
        "horizontal_corridor",
        2,
        0.0,
        lane_min=0.65,
        lane_max=0.90,
        longitudinal_stagger=1.50,
    )
    doorway_routes = compiler._moderate_routes(
        "doorway",
        2,
        0.0,
        lane_min=0.65,
        lane_max=0.90,
        longitudinal_stagger=1.50,
    )
    assert [route[-1][0] for route in head_routes] == [5.8, 6.05]
    assert [route[-1][0] for route in doorway_routes] == [12.0, 11.65]


def test_v2_compiler_emits_safe_behind_start_egress_without_overwriting_v1(
    tmp_path: Path,
) -> None:
    compiler = _compiler()
    output = tmp_path / "moderate_v2"
    summary = compiler.compile_benchmark(
        V2_CONFIG,
        output,
        validation_repetitions=1,
        test_repetitions=1,
        render_previews=False,
    )
    assert summary["benchmark_id"] == "moderate_social_navigation_v2"
    assert summary["manifest_suffix"] == "moderate_v2"
    assert summary["scenario_count"] == 48
    assert not (output / "splits/moderate_validation.yaml").exists()

    for split in ("validation", "test"):
        manifest = _manifest(output, split, "moderate_v2")
        committed_manifest = _manifest(ROOT / "scenarios", split, "moderate_v2")
        assert [
            (row["scenario_id"], row["seed"], row["sha256"]) for row in manifest["scenarios"]
        ] == [
            (row["scenario_id"], row["seed"], row["sha256"])
            for row in committed_manifest["scenarios"]
        ]
        for record in manifest["scenarios"]:
            scenario_path = output / "generated" / record["path"]
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            actors = scenario["obstacles"]["dynamic"]
            assert all(actor["robot_avoidance_distance_m"] == 0.90 for actor in actors)
            assert all("actor_dynamics_version" not in actor for actor in actors)
            assert "actor_dynamics_version" not in scenario["ramp_metadata"]
            family = record["family"]
            if family not in {"head_on_corridor", "doorway_bottleneck"}:
                continue
            expected_exit = 3.0 if family == "head_on_corridor" else 5.0
            robot_start_x = float(scenario["robots"][0]["start"][0])
            assert all(float(actor["waypoints"][-1][0]) == expected_exit for actor in actors)
            assert all(float(actor["waypoints"][-1][0]) < robot_start_x for actor in actors)
            moderation = scenario["ramp_metadata"]["moderation"]
            exit_key = "head_on_exit_x_m" if family == "head_on_corridor" else "doorway_exit_x_m"
            assert moderation[exit_key] == expected_exit


def test_v2_validation_rejects_unsafe_clearance_and_egress() -> None:
    compiler = _compiler()
    config = yaml.safe_load(V2_CONFIG.read_text(encoding="utf-8"))
    unsafe_clearance = copy.deepcopy(config)
    unsafe_clearance["moderation"]["robot_avoidance_distance_m"] = 0.71
    with pytest.raises(ValueError, match=r"must exceed the 0\.71 m combined collision radii"):
        compiler._validate_config(unsafe_clearance)

    forward_exit = copy.deepcopy(config)
    forward_exit["moderation"]["head_on_exit_x_m"] = 5.0
    with pytest.raises(ValueError, match="must lie behind the head_on_corridor robot start"):
        compiler._validate_config(forward_exit)


def test_configured_egress_endpoint_must_be_free_of_static_geometry() -> None:
    compiler = _compiler()
    scenario = {
        "ramp_metadata": {"family": "head_on_corridor"},
        "robots": [{"start": [5.0, 12.0, 0.0]}],
        "obstacles": {
            "static": [
                {
                    "name": "blocking_shelf",
                    "model": "shelf",
                    "pos": [3.0, 12.0, 0.0],
                }
            ],
            "dynamic": [
                {
                    "name": "ped_00",
                    "radius": 0.35,
                    "waypoints": [[10.0, 12.0, 0.0], [3.0, 12.0, 0.0]],
                }
            ],
        },
    }
    with pytest.raises(ValueError, match="egress endpoint intersects inflated static geometry"):
        compiler._validate_configured_egress_endpoints(
            scenario,
            [0.0, 31.28, 0.0, 24.03],
            0.10,
            {"head_on_exit_x_m": 3.0},
        )


def test_compiler_generates_split_safe_one_shot_scenarios_and_previews(
    tmp_path: Path,
) -> None:
    compiler = _compiler()
    output = tmp_path / "moderate"
    summary = compiler.compile_benchmark(
        CONFIG,
        output,
        validation_repetitions=1,
        test_repetitions=1,
        render_previews=True,
    )
    assert summary["scenario_count"] == 48
    assert summary["counts_by_split"] == {"validation": 24, "test": 24}
    assert summary["footprint_inflation_m"] == pytest.approx(0.40)

    split_sets: dict[str, dict[str, set[object]]] = {}
    for split, seed_floor in (("validation", 51000), ("test", 61000)):
        manifest = _manifest(output, split)
        assert manifest["split"] == split
        assert manifest["difficulty"] == "moderate"
        records = manifest["scenarios"]
        assert len(records) == 24
        assert {record["family"] for record in records} == FAMILIES
        assert {record["density"] for record in records} == {"low", "medium", "high"}
        assert {record["replicate"] for record in records} == {0}
        assert min(int(record["seed"]) for record in records) >= seed_floor
        assert max(int(record["seed"]) for record in records) < seed_floor + 1000

        identifiers: set[object] = set()
        seeds: set[object] = set()
        hashes: set[object] = set()
        for record in records:
            scenario_path = output / "generated" / record["path"]
            preview_path = output / record["preview"]
            assert scenario_path.is_file()
            assert preview_path.is_file() and preview_path.stat().st_size > 0
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == record["sha256"]
            scenario = json.loads(serialized)
            metadata = scenario["ramp_metadata"]
            assert metadata["scenario_id"] == record["scenario_id"]
            assert metadata["split"] == split
            assert metadata["seed"] == record["seed"]
            assert metadata["difficulty"] == "moderate"
            assert metadata["moderation"]["corridor_footprint_clear_width_m"] == 2.6
            assert metadata["moderation"]["doorway_footprint_clear_width_m"] == 2.3
            actors = scenario["obstacles"]["dynamic"]
            assert len(actors) == {"low": 1, "medium": 2, "high": 4}[record["density"]]
            assert all(actor["cyclic_goals"] is False for actor in actors)
            assert all(actor["behavior"]["once"] is True for actor in actors)
            assert all(actor["robot_avoidance_distance_m"] == 1.50 for actor in actors)
            assert all("actor_dynamics_version" not in actor for actor in actors)
            assert "actor_dynamics_version" not in metadata
            if record["family"] == "group_blocking":
                assert min(float(actor["pos"][1]) for actor in actors) >= 12.85
            _, path = compiler._footprint_path(
                scenario,
                [0.0, 31.28, 0.0, 24.03],
                0.10,
                0.40,
            )
            assert path
            if record["family"] == "head_on_corridor":
                south = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "south_moderate" in item["name"]
                ]
                north = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "north_moderate" in item["name"]
                ]
                footprint_clear_width = (
                    min(float(item["pos"][1]) for item in north)
                    - max(float(item["pos"][1]) for item in south)
                    - 2.0 * (0.20 + 0.40)
                )
                assert footprint_clear_width == pytest.approx(2.60)
            if record["family"] == "doorway_bottleneck":
                south = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "doorwall_south_moderate" in item["name"]
                ]
                north = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "doorwall_north_moderate" in item["name"]
                ]
                footprint_clear_width = (
                    min(float(item["pos"][1]) for item in north)
                    - max(float(item["pos"][1]) for item in south)
                    - 2.0 * (0.45 + 0.40)
                )
                assert footprint_clear_width == pytest.approx(2.30)
            if record["family"] == "blind_corner":
                grid, _ = compiler._footprint_path(
                    scenario,
                    [0.0, 31.28, 0.0, 24.03],
                    0.10,
                    0.40,
                )
                assert all(
                    grid.is_free(grid.world_to_grid(float(point[0]), float(point[1])))
                    for actor in actors
                    for point in actor["waypoints"]
                )
            identifiers.add(record["scenario_id"])
            seeds.add(record["seed"])
            hashes.add(record["sha256"])
        assert len(identifiers) == len(records)
        assert len(seeds) == len(records)
        assert len(hashes) == len(records)
        split_sets[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for key in ("ids", "seeds", "hashes"):
        assert split_sets["validation"][key].isdisjoint(split_sets["test"][key])


def test_v3_compiler_emits_lane_preserving_stream_and_behavior_metadata(
    v3_compilation: tuple[Any, Path, dict[str, Any]],
) -> None:
    compiler, output, summary = v3_compilation
    assert summary["benchmark_id"] == "moderate_social_navigation_v3"
    assert summary["manifest_suffix"] == "moderate_v3"
    assert summary["counts_by_split"] == {"train": 24, "validation": 24, "test": 24}
    assert summary["scenario_count"] == 72
    assert {split: summary[f"{split}_seed_base"] for split in ("train", "validation", "test")} == {
        "train": 70000,
        "validation": 71000,
        "test": 81000,
    }

    split_values: dict[str, dict[str, set[object]]] = {}
    for split, seed_floor in (("train", 70000), ("validation", 71000), ("test", 81000)):
        manifest = _manifest(output, split, "moderate_v3")
        assert manifest["split"] == split
        records = manifest["scenarios"]
        assert len(records) == 24
        assert min(int(row["seed"]) for row in records) >= seed_floor
        assert max(int(row["seed"]) for row in records) < seed_floor + 1000
        identifiers: set[object] = set()
        seeds: set[object] = set()
        hashes: set[object] = set()
        doorway_sides: set[int] = set()
        for record in records:
            scenario_path = output / "generated" / record["path"]
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == record["sha256"]
            scenario = json.loads(serialized)
            metadata = scenario["ramp_metadata"]
            behavior_parameters = {
                "robot_soft_yield_distance_m": 0.90,
                "robot_hard_guard_distance_m": 0.73,
                "actor_update_frequency_hz": 5.0,
            }
            assert metadata["actor_dynamics_version"] == ("deterministic_one_shot_swept_guard_v1")
            assert metadata["actor_behavior_parameters"] == behavior_parameters
            assert all(
                actor["actor_dynamics_version"] == "deterministic_one_shot_swept_guard_v1"
                for actor in scenario["obstacles"]["dynamic"]
            )
            assert all(
                {
                    key: actor["behavior"][key]
                    for key in (
                        "robot_soft_yield_distance_m",
                        "robot_hard_guard_distance_m",
                        "actor_update_frequency_hz",
                    )
                }
                == behavior_parameters
                for actor in scenario["obstacles"]["dynamic"]
            )
            if record["family"] == "doorway_bottleneck":
                stream = metadata["doorway_stream"]
                side = int(stream["lane_side"])
                doorway_sides.add(side)
                assert side == compiler._seeded_doorway_lane_side(int(record["seed"]))
                assert stream["lane_offset_m"] == 0.75
                assert stream["lane_preserving"] is True
                lane_y = float(stream["lane_y_m"])
                recovery_y = float(stream["recovery_channel_y_m"])
                actors = scenario["obstacles"]["dynamic"]
                assert all(
                    all(float(point[1]) == pytest.approx(lane_y) for point in actor["waypoints"])
                    for actor in actors
                )
                starts = sorted(float(actor["waypoints"][0][0]) for actor in actors)
                assert all(right - left == pytest.approx(1.50) for left, right in pairwise(starts))
                assert all(float(actor["waypoints"][-1][0]) == 5.0 for actor in actors)
                grid = compiler._footprint_occupancy(
                    scenario,
                    [0.0, 31.28, 0.0, 24.03],
                    0.10,
                    0.40,
                )
                robot = scenario["robots"][0]
                assert grid.segment_is_free(
                    (float(robot["start"][0]), recovery_y),
                    (float(robot["goal"][0]), recovery_y),
                )
                assert (lane_y - 12.0) * (recovery_y - 12.0) < 0.0
            identifiers.add(record["scenario_id"])
            seeds.add(record["seed"])
            hashes.add(record["sha256"])
        assert doorway_sides == {-1, 1}
        assert len(identifiers) == len(records)
        assert len(seeds) == len(records)
        assert len(hashes) == len(records)
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for left, right in combinations(("train", "validation", "test"), 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])


def test_compiler_changes_do_not_modify_committed_v3_r0_hashes(
    v3_compilation: tuple[Any, Path, dict[str, Any]],
) -> None:
    _, output, _ = v3_compilation
    for split in ("train", "validation", "test"):
        generated = _manifest(output, split, "moderate_v3")["scenarios"]
        committed = _manifest(ROOT / "scenarios", split, "moderate_v3")["scenarios"]
        assert [(row["scenario_id"], row["seed"], row["sha256"]) for row in generated] == [
            (row["scenario_id"], row["seed"], row["sha256"]) for row in committed
        ]


def test_v4_compiler_emits_same_side_head_on_stream_with_free_channel(
    v4_compilation: tuple[Any, Path, dict[str, Any]],
) -> None:
    compiler, output, summary = v4_compilation
    assert summary["benchmark_id"] == "moderate_social_navigation_v4"
    assert summary["manifest_suffix"] == "moderate_v4"
    assert summary["counts_by_split"] == {"train": 24, "validation": 24, "test": 24}
    assert summary["scenario_count"] == 72
    assert summary["scenario_ids_sha256"]

    split_values: dict[str, dict[str, set[object]]] = {}
    expected_seed_bases = {"train": 72000, "validation": 73000, "test": 83000}
    for split, seed_floor in expected_seed_bases.items():
        records = _manifest(output, split, "moderate_v4")["scenarios"]
        assert len(records) == 24
        identifiers: set[object] = set()
        seeds: set[object] = set()
        hashes: set[object] = set()
        head_on_sides: set[int] = set()
        for record in records:
            assert seed_floor <= int(record["seed"]) < seed_floor + 1000
            scenario_path = output / "generated" / record["path"]
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == record["sha256"]
            scenario = json.loads(serialized)
            _, static_path = compiler._footprint_path(
                scenario,
                [0.0, 31.28, 0.0, 24.03],
                0.10,
                0.40,
            )
            assert static_path
            if record["family"] == "head_on_corridor":
                metadata = scenario["ramp_metadata"]
                stream = metadata["head_on_stream"]
                side = int(stream["lane_side"])
                head_on_sides.add(side)
                assert side == compiler._seeded_doorway_lane_side(int(record["seed"]))
                assert stream["lane_offset_m"] == 0.75
                assert stream["lane_preserving"] is True
                assert stream["seed_deterministic"] is True
                lane_y = float(stream["lane_y_m"])
                recovery_y = float(stream["recovery_channel_y_m"])
                actors = scenario["obstacles"]["dynamic"]
                assert len(actors) == {"low": 1, "medium": 2, "high": 4}[record["density"]]
                assert all(
                    all(float(point[1]) == pytest.approx(lane_y) for point in actor["waypoints"])
                    for actor in actors
                )
                assert all(actor["cyclic_goals"] is False for actor in actors)
                assert all(actor["behavior"]["once"] is True for actor in actors)
                starts = sorted(float(actor["waypoints"][0][0]) for actor in actors)
                assert all(right - left == pytest.approx(1.50) for left, right in pairwise(starts))
                assert abs(lane_y - recovery_y) == pytest.approx(1.50)
                assert (lane_y - 12.0) * (recovery_y - 12.0) < 0.0
                grid = compiler._footprint_occupancy(
                    scenario,
                    [0.0, 31.28, 0.0, 24.03],
                    0.10,
                    0.40,
                )
                robot = scenario["robots"][0]
                assert grid.segment_is_free(
                    (float(robot["start"][0]), recovery_y),
                    (float(robot["goal"][0]), recovery_y),
                )
            identifiers.add(record["scenario_id"])
            seeds.add(record["seed"])
            hashes.add(record["sha256"])
        assert head_on_sides <= {-1, 1}
        assert head_on_sides
        assert len(identifiers) == len(records)
        assert len(seeds) == len(records)
        assert len(hashes) == len(records)
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for left, right in combinations(("train", "validation", "test"), 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])


def test_v5_extensions_do_not_modify_committed_v4_r0_hashes(
    v4_compilation: tuple[Any, Path, dict[str, Any]],
) -> None:
    _, output, _ = v4_compilation
    for split in ("train", "validation", "test"):
        generated = _manifest(output, split, "moderate_v4")["scenarios"]
        committed = _manifest(ROOT / "scenarios", split, "moderate_v4")["scenarios"]
        assert [(row["scenario_id"], row["seed"], row["sha256"]) for row in generated] == [
            (row["scenario_id"], row["seed"], row["sha256"])
            for row in committed
            if row["replicate"] == 0
        ]


def test_v5_compiler_emits_recoverable_clearances_and_static_free_actor_routes(
    v5_compilation: tuple[Any, Path, dict[str, Any]],
) -> None:
    compiler, output, summary = v5_compilation
    assert summary["benchmark_id"] == "moderate_social_navigation_v5"
    assert summary["manifest_suffix"] == "moderate_v5"
    assert summary["counts_by_split"] == {"train": 24, "validation": 24, "test": 24}
    assert summary["scenario_count"] == 72
    expected_seed_bases = {"train": 74000, "validation": 75000, "test": 85000}
    split_values: dict[str, dict[str, set[object]]] = {}
    for split, seed_floor in expected_seed_bases.items():
        records = _manifest(output, split, "moderate_v5")["scenarios"]
        assert len(records) == 24
        identifiers: set[object] = set()
        seeds: set[object] = set()
        hashes: set[object] = set()
        for record in records:
            assert seed_floor <= int(record["seed"]) < seed_floor + 1000
            scenario_path = output / "generated" / record["path"]
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == record["sha256"]
            scenario = json.loads(serialized)
            _, static_path = compiler._footprint_path(
                scenario,
                [0.0, 31.28, 0.0, 24.03],
                0.10,
                0.40,
            )
            assert static_path
            actors = scenario["obstacles"]["dynamic"]
            for actor in actors:
                grid = compiler._footprint_occupancy(
                    scenario,
                    [0.0, 31.28, 0.0, 24.03],
                    0.10,
                    float(actor["radius"]),
                )
                points = [(float(point[0]), float(point[1])) for point in actor["waypoints"]]
                assert all(grid.is_free(grid.world_to_grid(*point)) for point in points)
                assert all(grid.segment_is_free(left, right) for left, right in pairwise(points))

            family = str(record["family"])
            if family == "blind_corner":
                vertical = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "corner_v_moderate" in item["name"]
                ]
                horizontal = [
                    item
                    for item in scenario["obstacles"]["static"]
                    if "corner_h_moderate" in item["name"]
                ]
                assert max(float(item["pos"][1]) for item in vertical) == pytest.approx(10.80)
                assert min(float(item["pos"][0]) for item in horizontal) == pytest.approx(15.50)
                inflated_dx = 15.50 - 0.45 - 0.40 - (13.50 + 0.20 + 0.40)
                inflated_dy = 12.80 - 0.20 - 0.40 - (10.80 + 0.45 + 0.40)
                assert (inflated_dx**2 + inflated_dy**2) ** 0.5 >= 0.70
            elif family == "group_blocking":
                nearest_centerline_offset = min(
                    abs(float(actor["waypoints"][0][1]) - 12.0) for actor in actors
                )
                assert nearest_centerline_offset >= 1.03
            elif family in {"overtaking", "opposite_streams"}:
                lane_offsets = [abs(float(actor["waypoints"][0][1]) - 12.0) for actor in actors]
                assert min(lane_offsets) >= 0.84 - 1.0e-9
                assert max(lane_offsets) <= 1.28 + 1.0e-9
            elif family == "temporary_blockage":
                assert all(len(actor["waypoints"]) == 3 for actor in actors)
                cross_x = sorted(float(actor["waypoints"][1][0]) for actor in actors)
                assert all(right - left == pytest.approx(0.80) for left, right in pairwise(cross_x))
                assert all(
                    abs(float(actor["waypoints"][0][0]) - float(actor["waypoints"][1][0]))
                    == pytest.approx(1.40)
                    for actor in actors
                )
                assert all(
                    abs(float(actor["waypoints"][0][1]) - float(actor["waypoints"][-1][1]))
                    == pytest.approx(2.00)
                    for actor in actors
                )
            identifiers.add(record["scenario_id"])
            seeds.add(record["seed"])
            hashes.add(record["sha256"])
        assert len(identifiers) == len(records)
        assert len(seeds) == len(records)
        assert len(hashes) == len(records)
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for left, right in combinations(("train", "validation", "test"), 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])


def test_committed_v4_full_and_smoke_manifests_are_complete_and_hash_valid() -> None:
    summary = json.loads(
        (ROOT / "scenarios/manifests/scenario_catalog_moderate_v4.json").read_text(encoding="utf-8")
    )
    assert summary["counts_by_split"] == {"train": 72, "validation": 72, "test": 120}
    assert summary["scenario_count"] == 264
    expected_counts = {"train": 72, "validation": 72, "test": 120}
    split_values: dict[str, dict[str, set[object]]] = {}
    validation_rows: dict[str, dict[str, Any]] = {}
    for split, expected_count in expected_counts.items():
        records = _manifest(ROOT / "scenarios", split, "moderate_v4")["scenarios"]
        assert len(records) == expected_count
        identifiers = {row["scenario_id"] for row in records}
        seeds = {row["seed"] for row in records}
        hashes = {row["sha256"] for row in records}
        assert len(identifiers) == expected_count
        assert len(seeds) == expected_count
        assert len(hashes) == expected_count
        for row in records:
            scenario_path = ROOT / "scenarios/generated" / row["path"]
            preview_path = ROOT / "scenarios" / row["preview"]
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == row["sha256"]
            assert preview_path.is_file() and preview_path.stat().st_size > 0
        if split == "validation":
            validation_rows = {row["scenario_id"]: row for row in records}
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for left, right in combinations(("train", "validation", "test"), 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])

    smoke = yaml.safe_load(
        (ROOT / "scenarios/splits/moderate_v4_validation_smoke.yaml").read_text(encoding="utf-8")
    )
    expected_conditions = {
        ("head_on_corridor", "low"),
        ("head_on_corridor", "medium"),
        ("head_on_corridor", "high"),
        ("doorway_bottleneck", "medium"),
        ("doorway_bottleneck", "high"),
        ("crossing_flow", "medium"),
    }
    assert len(smoke["scenarios"]) == 6
    assert {(row["family"], row["density"]) for row in smoke["scenarios"]} == (expected_conditions)
    assert all(row["replicate"] == 0 for row in smoke["scenarios"])
    assert all(validation_rows[row["scenario_id"]] == row for row in smoke["scenarios"])


def test_committed_v5_manifests_are_complete_hash_valid_and_smoke_is_predeclared() -> None:
    summary = json.loads(
        (ROOT / "scenarios/manifests/scenario_catalog_moderate_v5.json").read_text(encoding="utf-8")
    )
    assert summary["counts_by_split"] == {"train": 72, "validation": 72, "test": 120}
    assert summary["scenario_count"] == 264
    expected_counts = {"train": 72, "validation": 72, "test": 120}
    split_values: dict[str, dict[str, set[object]]] = {}
    validation_rows: dict[str, dict[str, Any]] = {}
    for split, expected_count in expected_counts.items():
        records = _manifest(ROOT / "scenarios", split, "moderate_v5")["scenarios"]
        assert len(records) == expected_count
        identifiers = {row["scenario_id"] for row in records}
        seeds = {row["seed"] for row in records}
        hashes = {row["sha256"] for row in records}
        assert len(identifiers) == expected_count
        assert len(seeds) == expected_count
        assert len(hashes) == expected_count
        for row in records:
            scenario_path = ROOT / "scenarios/generated" / row["path"]
            preview_path = ROOT / "scenarios" / row["preview"]
            serialized = scenario_path.read_text(encoding="utf-8")
            assert hashlib.sha256(serialized.encode()).hexdigest() == row["sha256"]
            assert preview_path.is_file() and preview_path.stat().st_size > 0
        if split == "validation":
            validation_rows = {row["scenario_id"]: row for row in records}
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}

    for left, right in combinations(("train", "validation", "test"), 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])

    smoke = yaml.safe_load(
        (ROOT / "scenarios/splits/moderate_v5_validation_calibration_smoke.yaml").read_text(
            encoding="utf-8"
        )
    )
    expected_conditions = {
        ("head_on_corridor", "medium"),
        ("doorway_bottleneck", "high"),
        ("blind_corner", "low"),
        ("blind_corner", "high"),
        ("group_blocking", "high"),
        ("overtaking", "low"),
        ("overtaking", "medium"),
        ("opposite_streams", "low"),
        ("opposite_streams", "medium"),
        ("opposite_streams", "high"),
        ("temporary_blockage", "low"),
        ("temporary_blockage", "high"),
    }
    assert len(smoke["scenarios"]) == 12
    assert {(row["family"], row["density"]) for row in smoke["scenarios"]} == (expected_conditions)
    assert all(row["replicate"] == 0 for row in smoke["scenarios"])
    assert all(validation_rows[row["scenario_id"]] == row for row in smoke["scenarios"])


def test_v3_validation_rejects_partial_dynamics_and_seed_block_leakage() -> None:
    compiler = _compiler()
    config = yaml.safe_load(V3_CONFIG.read_text(encoding="utf-8"))
    incomplete = copy.deepcopy(config)
    del incomplete["moderation"]["robot_hard_guard_distance_m"]
    with pytest.raises(ValueError, match="actor dynamics configuration is incomplete"):
        compiler._validate_config(incomplete)

    unsafe_guard = copy.deepcopy(config)
    unsafe_guard["moderation"]["robot_hard_guard_distance_m"] = 0.71
    with pytest.raises(ValueError, match="hard guard must exceed collision radii"):
        compiler._validate_config(unsafe_guard)

    overlapping = copy.deepcopy(config)
    overlapping["splits"]["validation"]["seed_base"] = 70500
    with pytest.raises(
        ValueError, match="train/validation seed blocks must differ and not overlap"
    ):
        compiler._validate_config(overlapping)


def test_v4_validation_rejects_partial_or_invalid_head_on_lane_stream() -> None:
    compiler = _compiler()
    config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    incomplete = copy.deepcopy(config)
    del incomplete["moderation"]["head_on_lane_offset_m"]
    with pytest.raises(ValueError, match="head-on lane-stream configuration is incomplete"):
        compiler._validate_config(incomplete)

    invalid_offset = copy.deepcopy(config)
    invalid_offset["moderation"]["head_on_lane_offset_m"] = 0.60
    with pytest.raises(ValueError, match="head-on lane offset must lie inside"):
        compiler._validate_config(invalid_offset)


def test_v5_validation_rejects_partial_or_zero_margin_calibration() -> None:
    compiler = _compiler()
    config = yaml.safe_load(V5_CONFIG.read_text(encoding="utf-8"))
    incomplete = copy.deepcopy(config)
    del incomplete["moderation"]["temporary_crossing_lead_in_m"]
    with pytest.raises(ValueError, match="v5 calibration configuration is incomplete"):
        compiler._validate_config(incomplete)

    narrow_chamfer = copy.deepcopy(config)
    narrow_chamfer["moderation"]["blind_corner_vertical_end_y_m"] = 11.50
    narrow_chamfer["moderation"]["blind_corner_horizontal_start_x_m"] = 14.50
    with pytest.raises(ValueError, match="footprint-clear chamfer"):
        compiler._validate_config(narrow_chamfer)

    near_guard_lane = copy.deepcopy(config)
    near_guard_lane["moderation"]["overtaking_lane_offset_range_m"] = [0.78, 1.10]
    with pytest.raises(ValueError, match="overtaking_lane_offset_range_m"):
        compiler._validate_config(near_guard_lane)


def test_cli_overrides_are_deterministic_and_isolate_suffix_outputs(tmp_path: Path) -> None:
    compiler = _compiler()
    first = tmp_path / "first"
    second = tmp_path / "second"
    options = {
        "validation_repetitions": 2,
        "test_repetitions": 1,
        "validation_seed_base": 52000,
        "test_seed_base": 62000,
        "manifest_suffix": "moderate_ci",
        "render_previews": False,
    }
    summary_first = compiler.compile_benchmark(CONFIG, first, **options)
    summary_second = compiler.compile_benchmark(CONFIG, second, **options)
    assert summary_first == summary_second
    assert summary_first["counts_by_split"] == {"validation": 48, "test": 24}
    assert (first / "splits/moderate_ci_validation.yaml").is_file()
    assert (first / "splits/moderate_ci_test.yaml").is_file()

    first_validation = _manifest(first, "validation", "moderate_ci")
    second_validation = _manifest(second, "validation", "moderate_ci")
    assert first_validation == second_validation
    assert all("_moderate_ci_" in row["scenario_id"] for row in first_validation["scenarios"])
    assert all(
        row["path"].startswith("moderate_ci/arena/map_empty/")
        for row in first_validation["scenarios"]
    )
    for row in first_validation["scenarios"]:
        left = first / "generated" / row["path"]
        right = second / "generated" / row["path"]
        assert left.read_bytes() == right.read_bytes()

    args = compiler.parse_args(
        [
            "--validation-repetitions",
            "2",
            "--test-repetitions",
            "1",
            "--validation-seed-base",
            "52000",
            "--test-seed-base",
            "62000",
            "--manifest-suffix",
            "moderate_ci",
            "--no-previews",
        ]
    )
    assert args.validation_repetitions == 2
    assert args.test_repetitions == 1
    assert args.manifest_suffix == "moderate_ci"
    assert args.no_previews is True


def test_v3_cli_exposes_train_split_overrides() -> None:
    compiler = _compiler()
    args = compiler.parse_args(
        [
            "--config",
            str(V3_CONFIG),
            "--train-repetitions",
            "1",
            "--train-seed-base",
            "72000",
            "--no-previews",
        ]
    )
    assert args.config == V3_CONFIG
    assert args.train_repetitions == 1
    assert args.train_seed_base == 72000
    assert args.no_previews is True


def test_compiler_rejects_seed_and_suffix_leakage(tmp_path: Path) -> None:
    compiler = _compiler()
    with pytest.raises(ValueError, match="seed blocks must differ"):
        compiler.compile_benchmark(
            CONFIG,
            tmp_path / "same_seed",
            validation_repetitions=1,
            test_repetitions=1,
            validation_seed_base=51000,
            test_seed_base=51000,
            render_previews=False,
        )
    with pytest.raises(ValueError, match="manifest suffix"):
        compiler.compile_benchmark(
            CONFIG,
            tmp_path / "bad_suffix",
            validation_repetitions=1,
            test_repetitions=1,
            manifest_suffix="../escape",
            render_previews=False,
        )
