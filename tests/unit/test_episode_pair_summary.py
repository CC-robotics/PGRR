from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


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
                "project_commit": "abc123",
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
            "robot_pose": [0.0, 0.0, 0.0],
            "goal": [2.0, 0.0, 0.0],
            "privileged": {
                "nearest_human_distance": 1.2,
                "robot_pose": [0.0, 0.0, 0.0],
            },
        },
        {
            "timestamp": 1.0,
            "distance_to_goal": 0.2,
            "nearest_obstacle_distance": 0.8,
            "recovery_action": 3,
            "robot_pose": [1.8, 0.0, 0.0],
            "goal": [2.0, 0.0, 0.0],
            "privileged": {
                "nearest_human_distance": 0.9,
                "robot_pose": [1.75, 0.0, 0.0],
            },
        },
    ]
    prefix.with_suffix(".jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    result = module.summarize(prefix)
    assert result["progress_m"] == 1.8
    assert result["min_human_distance_m"] == 0.9
    assert result["recovery_actions"] == 1
    assert result["actual_goal_distance_m"] == 0.25
    assert result["actual_goal_distance_source"] == "last_sample"
    assert result["max_localization_error_m"] == pytest.approx(0.05)
    assert result["project_commit"] == "abc123"

    prefix.with_suffix(".outcome.json").write_text(
        json.dumps(
            {
                "outcome": "GOAL_REACHED",
                "localized_goal_distance_m": 0.18,
                "physical_goal_distance_m": 0.19,
            }
        ),
        encoding="utf-8",
    )
    terminal_result = module.summarize(prefix)
    assert terminal_result["actual_goal_distance_m"] == 0.19
    assert terminal_result["actual_goal_distance_source"] == "outcome_terminal_snapshot"
