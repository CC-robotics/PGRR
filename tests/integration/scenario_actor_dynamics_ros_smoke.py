#!/usr/bin/env python3
"""Validate ROS actor-route loading against the committed v3 contract."""

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

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_V3_SCENARIO = (
    REPOSITORY_ROOT
    / "scenarios/generated/moderate_v3/arena/map_empty"
    / "head_on_corridor_low_validation_moderate_v3_r00_s71000.json"
)
COMMITTED_V3_DYNAMICS_VERSION = "deterministic_one_shot_swept_guard_v1"


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
        actor.update(
            {
                "actor_dynamics_version": COMMITTED_V3_DYNAMICS_VERSION,
                "actor_update_frequency_hz": 5.0,
                "robot_soft_yield_distance_m": 0.90,
                "robot_hard_guard_distance_m": 0.73,
            }
        )
        metadata["actor_dynamics_version"] = COMMITTED_V3_DYNAMICS_VERSION
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


def _load_path(path: Path) -> ActorRoute:
    routes = ScenarioActorController._load_routes(path)
    assert len(routes) == 1
    return routes[0]


def main() -> int:
    assert SWEPT_GUARD_DYNAMICS_VERSION == COMMITTED_V3_DYNAMICS_VERSION

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

    committed_payload = json.loads(COMMITTED_V3_SCENARIO.read_text(encoding="utf-8"))
    committed_actor = committed_payload["obstacles"]["dynamic"][0]
    assert committed_actor["actor_dynamics_version"] == COMMITTED_V3_DYNAMICS_VERSION
    committed = _load_path(COMMITTED_V3_SCENARIO)
    assert committed.dynamics_version == committed_actor["actor_dynamics_version"]
    assert committed.uses_swept_guard
    assert committed.update_frequency_hz == committed_actor["actor_update_frequency_hz"]
    assert committed.soft_yield_distance_m == committed_actor["robot_soft_yield_distance_m"]
    assert committed.hard_collision_guard_m == committed_actor["robot_hard_guard_distance_m"]
    print(
        "PASS: legacy compatibility and committed moderate_v3 actor contract "
        f"({COMMITTED_V3_DYNAMICS_VERSION})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
