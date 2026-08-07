from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _compiler_module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "data" / "compile_scenarios.py"
    spec = importlib.util.spec_from_file_location("compile_scenarios", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_is_deterministic_and_split_safe(tmp_path: Path) -> None:
    compiler = _compiler_module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    summary_first = compiler.compile_catalog(
        ROOT / "configs" / "experiments" / "scenario_catalog.yaml", first, 17
    )
    summary_second = compiler.compile_catalog(
        ROOT / "configs" / "experiments" / "scenario_catalog.yaml", second, 17
    )
    assert summary_first == summary_second
    assert summary_first["scenario_count"] == 72
    split_ids: dict[str, set[str]] = {}
    for split in ("train", "validation", "test"):
        manifest = yaml.safe_load((first / "splits" / f"{split}.yaml").read_text())
        records = manifest["scenarios"]
        assert len(records) == 24
        assert {item["family"] for item in records} == {
            "head_on_corridor",
            "doorway_bottleneck",
            "crossing_flow",
            "blind_corner",
            "group_blocking",
            "overtaking",
            "opposite_streams",
            "temporary_blockage",
        }
        split_ids[split] = {item["scenario_id"] for item in records}
    assert split_ids["train"].isdisjoint(split_ids["validation"])
    assert split_ids["train"].isdisjoint(split_ids["test"])
    assert split_ids["validation"].isdisjoint(split_ids["test"])


def test_temporary_blockage_is_finite_one_shot_motion() -> None:
    compiler = _compiler_module()
    scenario = compiler._build_scenario(
        {
            "id": "temporary_blockage",
            "layout": "temporary_blockage",
            "robot_start": [7.0, 12.0, 0.0],
            "robot_goal": [24.0, 12.0, 0.0],
            "speed_range_mps": [0.1, 0.3],
        },
        density="high",
        count=6,
        split="train",
        seed=1720,
        offset=0.0,
        map_id="map_empty",
    )

    actors = scenario["obstacles"]["dynamic"]
    assert actors
    assert scenario["ramp_metadata"]["human_behavior_model"].startswith("deterministic one-shot")
    for actor in actors:
        assert actor["cyclic_goals"] is False
        assert actor["behavior"]["once"] is True
        assert actor["robot_avoidance_distance_m"] == 0.8
        start, goal = actor["waypoints"]
        assert abs(float(goal[1]) - float(start[1])) >= 8.0
        assert min(float(start[1]), float(goal[1])) < 8.6
        assert max(float(start[1]), float(goal[1])) > 15.4
