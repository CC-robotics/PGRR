from __future__ import annotations

from pathlib import Path

import yaml


def test_arena_task_boundary_exceeds_algorithm_episode_timeout() -> None:
    root = Path(__file__).resolve().parents[2]
    profile = yaml.safe_load(
        (root / "configs" / "platform" / "arena_task_generator_no_auto_reset.yaml").read_text()
    )
    parameters = profile["/**"]["ros__parameters"]
    assert parameters["auto_reset"] is False
    assert isinstance(parameters["timeout"], int)
    assert parameters["timeout"] > 120.0
