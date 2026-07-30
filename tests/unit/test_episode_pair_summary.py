from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script = Path(__file__).parents[2] / "scripts/evaluate/summarize_episode_pair.py"
    spec = importlib.util.spec_from_file_location("summarize_episode_pair", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pair_summary_uses_raw_episode_values(tmp_path: Path) -> None:
    module = _load_module()
    prefix = tmp_path / "episode"
    prefix.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "episode_id": "episode",
                "scenario_id": "scenario",
                "seed": 7,
                "source_policy": "oracle",
            }
        ),
        encoding="utf-8",
    )
    prefix.with_suffix(".outcome.json").write_text(
        json.dumps({"outcome": "GOAL_REACHED"}), encoding="utf-8"
    )
    rows = [
        {
            "timestamp": 0.0,
            "distance_to_goal": 2.0,
            "nearest_obstacle_distance": 1.0,
            "recovery_action": 24,
            "privileged": {"nearest_human_distance": 1.2},
        },
        {
            "timestamp": 1.0,
            "distance_to_goal": 0.2,
            "nearest_obstacle_distance": 0.8,
            "recovery_action": 3,
            "privileged": {"nearest_human_distance": 0.9},
        },
    ]
    prefix.with_suffix(".jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    result = module.summarize(prefix)
    assert result["progress_m"] == 1.8
    assert result["min_human_distance_m"] == 0.9
    assert result["recovery_actions"] == 1
