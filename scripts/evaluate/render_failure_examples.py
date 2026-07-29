#!/usr/bin/env python3
"""Render trajectory PDF and MP4 evidence from recorded Gate 1 episodes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EPISODES = (
    "head_on_corridor_high_mining_seed00_base_dwb",
    "doorway_bottleneck_high_mining_seed00_base_dwb",
    "crossing_flow_high_mining_seed00_base_dwb",
)


def _load_episode(episode_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    prefix = ROOT / "data" / "raw" / episode_id
    metadata = json.loads(prefix.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in prefix.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outcome = json.loads(prefix.with_suffix(".outcome.json").read_text(encoding="utf-8"))
    if not rows:
        raise ValueError(f"episode contains no rows: {episode_id}")
    return metadata, rows, outcome


def _draw_scene(axis: Axes, scenario: dict[str, Any]) -> None:
    axis.set_xlim(0.0, 31.28)
    axis.set_ylim(0.0, 24.03)
    axis.set_aspect("equal")
    for item in scenario["obstacles"]["static"]:
        x, y, yaw = (float(value) for value in item["pos"])
        width, height = (0.9, 0.4) if abs(math.cos(yaw)) >= abs(math.sin(yaw)) else (0.4, 0.9)
        axis.add_patch(
            Rectangle(
                (x - width / 2.0, y - height / 2.0),
                width,
                height,
                color="0.30",
                alpha=0.7,
            )
        )
    robot = scenario["robots"][0]
    axis.scatter(*robot["start"][:2], color="#2ca02c", s=45, label="start", zorder=5)
    axis.scatter(*robot["goal"][:2], color="#d62728", marker="*", s=90, label="goal", zorder=5)
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")


def _scenario(metadata: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / "scenarios" / "generated" / "mining" / f"{metadata['scenario_id']}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _human_tracks(rows: list[dict[str, Any]]) -> list[np.ndarray]:
    count = max(len(row["privileged"].get("human_positions", [])) for row in rows)
    tracks: list[list[list[float]]] = [[] for _ in range(count)]
    for row in rows:
        for index, position in enumerate(row["privileged"].get("human_positions", [])):
            tracks[index].append(position)
    return [np.asarray(track, dtype=np.float64) for track in tracks if track]


def _render_summary(
    episodes: list[tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]],
    destination: Path,
) -> None:
    figure, axes = plt.subplots(1, len(episodes), figsize=(15.0, 4.2), constrained_layout=True)
    axes_array = np.atleast_1d(axes)
    for axis, (metadata, rows, outcome) in zip(axes_array, episodes, strict=True):
        scenario = _scenario(metadata)
        _draw_scene(axis, scenario)
        robot = np.asarray([row["robot_pose"][:2] for row in rows], dtype=np.float64)
        axis.plot(robot[:, 0], robot[:, 1], color="#1f77b4", linewidth=2.0, label="robot")
        for index, track in enumerate(_human_tracks(rows)):
            axis.plot(
                track[:, 0],
                track[:, 1],
                color="#ff7f0e",
                alpha=0.45,
                linewidth=0.8,
                label="pedestrians" if index == 0 else None,
            )
        axis.set_title(
            f"{scenario['ramp_metadata']['family']}\n"
            f"{outcome['outcome']} at {rows[-1]['timestamp']:.1f} s"
        )
        axis.legend(loc="upper right", fontsize=7)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination)
    plt.close(figure)


def _render_video(
    metadata: dict[str, Any],
    rows: list[dict[str, Any]],
    outcome: dict[str, Any],
    destination: Path,
    max_frames: int,
) -> None:
    scenario = _scenario(metadata)
    indices = np.unique(np.linspace(0, len(rows) - 1, min(max_frames, len(rows)), dtype=int))
    robot = np.asarray([row["robot_pose"][:2] for row in rows], dtype=np.float64)
    figure, axis = plt.subplots(figsize=(7.2, 5.5), constrained_layout=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(destination, fps=10, codec="libx264", quality=7) as writer:
        for index in indices:
            axis.clear()
            _draw_scene(axis, scenario)
            axis.plot(robot[: index + 1, 0], robot[: index + 1, 1], color="#1f77b4", linewidth=2.0)
            axis.scatter(*robot[index], color="#1f77b4", s=55, zorder=6)
            humans = rows[index]["privileged"].get("human_positions", [])
            if humans:
                positions = np.asarray(humans, dtype=np.float64)
                axis.scatter(positions[:, 0], positions[:, 1], color="#ff7f0e", s=45, zorder=6)
            axis.set_title(
                f"{metadata['scenario_id']} | t={rows[index]['timestamp']:.1f} s | "
                f"{outcome['outcome']}"
            )
            figure.canvas.draw()
            writer.append_data(np.asarray(figure.canvas.buffer_rgba())[:, :, :3])
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", nargs="+", default=DEFAULT_EPISODES)
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs" / "figures" / "baseline_failure_trajectories.pdf",
    )
    parser.add_argument("--video-directory", type=Path, default=ROOT / "outputs" / "videos")
    parser.add_argument("--max-video-frames", type=int, default=150)
    args = parser.parse_args()
    if args.max_video_frames <= 0:
        raise ValueError("max_video_frames must be positive")
    episodes = [_load_episode(episode_id) for episode_id in args.episodes]
    _render_summary(episodes, args.summary.resolve())
    for metadata, rows, outcome in episodes:
        family = _scenario(metadata)["ramp_metadata"]["family"]
        destination = args.video_directory.resolve() / f"baseline_failure_{family}_seed00.mp4"
        _render_video(metadata, rows, outcome, destination, args.max_video_frames)
    print(f"Rendered {len(episodes)} failure examples")


if __name__ == "__main__":
    main()
