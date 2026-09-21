from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/replay_upstream_mask_layers.py"
    spec = importlib.util.spec_from_file_location("replay_upstream_mask_layers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_replay_isolates_each_upstream_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    report = module.build_report()
    counts = {
        fixture["fixture"]: [stage["retained_subgoal_count"] for stage in fixture["stages"]]
        for fixture in report["fixtures"]
    }

    assert counts["open_control"] == [21, 21, 21]
    assert counts["map_enclosed"] == [0, 0, 0]
    assert counts["lidar_close_returns"] == [21, 0, 0]
    assert counts["narrow_path_corridor"][0:2] == [21, 21]
    assert 0 < counts["narrow_path_corridor"][2] < 21
    assert report["claim_boundary"] == "synthetic_layer_replay_not_episode_ablation"


def test_trace_enabled_and_disabled_are_behaviorally_equivalent() -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)

    fixtures = (
        {},
        {"locally_enclosed": True},
        {"lidar_range_m": 0.30},
        {"corridor_width_m": 0.20},
    )
    for index, parameters in enumerate(fixtures):
        disabled = module.run_fixture(
            f"fixture_{index}", trace_enabled=False, **parameters
        )
        enabled = module.run_fixture(
            f"fixture_{index}", trace_enabled=True, **parameters
        )

        assert enabled["stages"] == disabled["stages"]
        assert enabled["selected_action_id"] == disabled["selected_action_id"]
        assert disabled["trace"]["transitions"] == []
        assert len(enabled["trace"]["transitions"]) == 3
