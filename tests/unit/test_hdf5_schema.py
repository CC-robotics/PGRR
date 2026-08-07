from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest
from ramp_core.data.hdf5 import validate_file, write_episode
from ramp_core.data.schema import EpisodeMetadata, EpisodeOutcome, NavigationStep


def _metadata(identifier: str = "episode-001") -> EpisodeMetadata:
    return EpisodeMetadata(
        episode_id=identifier,
        scenario_id="tiny_doorway_low_train_s01000",
        map_id="map_empty",
        seed=0,
        split="train",
        planner_id="dwb",
        source_policy="base",
        arena_commit="c2ff4a87",
        project_commit="test",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _step(timestamp: float) -> NavigationStep:
    return NavigationStep(
        timestamp=timestamp,
        robot_pose=np.asarray([1.0 + timestamp, 2.0, 0.0]),
        robot_velocity=np.asarray([0.2, 0.0]),
        cmd_vel=np.asarray([0.2, 0.0]),
        base_cmd_vel=np.asarray([0.2, 0.0]),
        goal=np.asarray([4.0, 2.0, 0.0]),
        distance_to_goal=3.0 - timestamp,
        global_path=((1.0, 2.0), (4.0, 2.0)),
        lidar=np.full(180, 5.0),
        nearest_obstacle_distance=5.0,
        planner_status=1,
        failure_prediction=np.asarray([0.1, 0.0, 0.0, 0.0]),
        failure_score=0.1,
        recovery_state=0,
        recovery_action=24,
        collision=False,
        timeout=False,
        recovery_reason="not_triggered",
        privileged={"nearest_human_distance": 1.8},
    )


def test_hdf5_round_trip_and_privileged_separation(tmp_path: Path) -> None:
    assert _step(0.0).as_jsonable()["recovery_reason"] == "not_triggered"
    destination = tmp_path / "episodes.h5"
    write_episode(destination, _metadata(), [_step(0.0), _step(0.1)], EpisodeOutcome.GOAL_REACHED)
    assert validate_file(destination) == {
        "episode_count": 1,
        "step_count": 2,
        "outcomes": {"GOAL_REACHED": 1},
    }
    with h5py.File(destination, "r") as handle:
        episode = handle["episodes"]["episode-001"]
        assert "nearest_human_distance" not in episode["observations"]
        assert episode["observations"]["failure_prediction"].shape == (2, 4)
        assert b"nearest_human_distance" in episode["privileged"]["json"][0]


def test_hdf5_rejects_duplicate_and_non_monotonic_episode(tmp_path: Path) -> None:
    destination = tmp_path / "episodes.h5"
    write_episode(destination, _metadata(), [_step(0.0)], EpisodeOutcome.TIMEOUT)
    with pytest.raises(ValueError, match="duplicate episode"):
        write_episode(destination, _metadata(), [_step(0.0)], EpisodeOutcome.TIMEOUT)
    with pytest.raises(ValueError, match="strictly increasing"):
        write_episode(
            destination,
            _metadata("episode-002"),
            [_step(1.0), _step(0.0)],
            EpisodeOutcome.INVALID_RESET,
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        write_episode(
            destination,
            _metadata("episode-003"),
            [_step(0.0), _step(0.0)],
            EpisodeOutcome.TIMEOUT,
        )
