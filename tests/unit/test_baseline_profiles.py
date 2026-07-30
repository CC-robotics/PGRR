from __future__ import annotations

from pathlib import Path

import yaml


def test_baseline_profiles_are_distinct_and_wired_into_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs" / "planner" / "baselines.yaml").read_text())
    profiles = config["profiles"]
    assert profiles["base"]["arena_inter_planner"] == profiles["heuristic"]["arena_inter_planner"]
    assert profiles["standard"]["arena_inter_planner"] != profiles["base"]["arena_inter_planner"]
    runtime = (root / "scripts" / "arena" / "run_baseline_episode_inner.sh").read_text()
    for profile in profiles.values():
        assert profile["arena_inter_planner"] in runtime
        assert len(profile["behavior_tree_sha256"]) == 64
    assert 'inter_planner:="${INTER_PLANNER}"' in runtime
