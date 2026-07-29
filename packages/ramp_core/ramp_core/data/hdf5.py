"""Validated HDF5 episode storage; one group per episode, never one file per frame."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import h5py  # type: ignore[import-untyped]
import numpy as np

from ramp_core.data.schema import EpisodeMetadata, EpisodeOutcome, NavigationStep


def write_episode(
    path: Path,
    metadata: EpisodeMetadata,
    steps: Sequence[NavigationStep],
    outcome: EpisodeOutcome,
) -> None:
    if not steps:
        raise ValueError("cannot write an empty episode")
    timestamps = np.asarray([step.timestamp for step in steps], dtype=np.float64)
    if np.any(np.diff(timestamps) < 0.0):
        raise ValueError("episode timestamps must be monotonic")
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "a") as handle:
        episodes = handle.require_group("episodes")
        if metadata.episode_id in episodes:
            raise ValueError(f"duplicate episode id: {metadata.episode_id}")
        group = episodes.create_group(metadata.episode_id)
        group.attrs["metadata_json"] = json.dumps(asdict(metadata), sort_keys=True)
        group.attrs["outcome"] = int(outcome)
        observations = group.create_group("observations")
        observations.create_dataset("timestamp", data=timestamps, compression="gzip")
        for name in ("robot_pose", "robot_velocity", "cmd_vel", "base_cmd_vel", "goal", "lidar"):
            observations.create_dataset(
                name,
                data=np.stack([getattr(step, name) for step in steps]),
                compression="gzip",
            )
        for name in ("distance_to_goal", "nearest_obstacle_distance"):
            observations.create_dataset(
                name,
                data=np.asarray([getattr(step, name) for step in steps], dtype=np.float32),
                compression="gzip",
            )
        for name in ("planner_status", "recovery_state", "recovery_action"):
            observations.create_dataset(
                name,
                data=np.asarray([getattr(step, name) for step in steps], dtype=np.int16),
                compression="gzip",
            )
        for name in ("collision", "timeout"):
            observations.create_dataset(
                name,
                data=np.asarray([getattr(step, name) for step in steps], dtype=np.bool_),
                compression="gzip",
            )
        float_vlen = h5py.vlen_dtype(np.dtype("float32"))
        paths = observations.create_dataset("global_path_flat", (len(steps),), dtype=float_vlen)
        path_lengths = np.empty(len(steps), dtype=np.int32)
        for index, step in enumerate(steps):
            flattened = np.asarray(step.global_path, dtype=np.float32).reshape(-1)
            paths[index] = flattened
            path_lengths[index] = len(step.global_path)
        observations.create_dataset("global_path_length", data=path_lengths, compression="gzip")
        privileged = group.create_group("privileged")
        string_type = h5py.string_dtype(encoding="utf-8")
        privileged.create_dataset(
            "json",
            data=np.asarray(
                [json.dumps(step.privileged, sort_keys=True) for step in steps], dtype=object
            ),
            dtype=string_type,
            compression="gzip",
        )


def validate_file(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        if "episodes" not in handle:
            raise ValueError("missing /episodes group")
        identifiers = sorted(handle["episodes"].keys())
        if not identifiers:
            raise ValueError("HDF5 file contains no episodes")
        total_steps = 0
        outcomes: dict[str, int] = {}
        for identifier in identifiers:
            group = handle["episodes"][identifier]
            observations = group["observations"]
            length = int(observations["timestamp"].shape[0])
            if observations["lidar"].shape != (length, 180):
                raise ValueError(f"invalid lidar shape in {identifier}")
            if np.any(np.diff(observations["timestamp"][:]) < 0.0):
                raise ValueError(f"non-monotonic timestamps in {identifier}")
            if group["privileged"]["json"].shape != (length,):
                raise ValueError(f"privileged/public time dimension mismatch in {identifier}")
            total_steps += length
            outcome_name = EpisodeOutcome(int(group.attrs["outcome"])).name
            outcomes[outcome_name] = outcomes.get(outcome_name, 0) + 1
        return {"episode_count": len(identifiers), "step_count": total_steps, "outcomes": outcomes}
