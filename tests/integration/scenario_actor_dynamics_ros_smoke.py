#!/usr/bin/env python3
"""Validate ROS actor-route loading for legacy and swept-guard scenarios."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ramp_ros.nodes.scenario_actor_controller_node import (
    LEGACY_DYNAMICS_VERSION,
    SWEPT_GUARD_DYNAMICS_VERSION,
    ActorRoute,
    ScenarioActorController,
)


def _scenario(*, swept_guard: bool) -> dict[str, object]:
    actor: dict[str, object] = {
        "name": "ped_00",
        "waypoints": [[2.0, 1.0, 0.0], [4.0, 1.0, 0.0]],
        "max_vel": 0.4,
        "cyclic_goals": False,
        "robot_avoidance_distance_m": 0.9,
    }
    metadata: dict[str, object] = {}
    if swept_guard:
        metadata["actor_dynamics"] = {
            "version": SWEPT_GUARD_DYNAMICS_VERSION,
            "soft_yield_distance_m": 0.90,
            "hard_collision_guard_m": 0.73,
            "maximum_soft_hold_s": 1.0,
            "update_frequency_hz": 5.0,
        }
    return {
        "ramp_metadata": metadata,
        "obstacles": {"dynamic": [actor]},
    }


def _load(payload: dict[str, object]) -> ActorRoute:
    with tempfile.TemporaryDirectory(prefix="pgrr_actor_dynamics_") as directory:
        path = Path(directory) / "scenario.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        routes = ScenarioActorController._load_routes(path)
    assert len(routes) == 1
    return routes[0]


def main() -> int:
    legacy = _load(_scenario(swept_guard=False))
    assert legacy.dynamics_version == LEGACY_DYNAMICS_VERSION
    assert not legacy.uses_swept_guard
    assert legacy.update_frequency_hz is None

    guarded = _load(_scenario(swept_guard=True))
    assert guarded.dynamics_version == SWEPT_GUARD_DYNAMICS_VERSION
    assert guarded.uses_swept_guard
    assert guarded.soft_yield_distance_m == 0.90
    assert guarded.hard_collision_guard_m == 0.73
    assert guarded.maximum_soft_hold_s == 1.0
    assert guarded.update_frequency_hz == 5.0
    print("PASS: legacy route compatibility and swept_guard_v1 fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
