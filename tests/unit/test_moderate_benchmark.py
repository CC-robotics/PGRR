from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate.yaml"
V2_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate_v2.yaml"
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
        for record in manifest["scenarios"]:
            scenario_path = output / "generated" / record["path"]
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            actors = scenario["obstacles"]["dynamic"]
            assert all(actor["robot_avoidance_distance_m"] == 0.90 for actor in actors)
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
