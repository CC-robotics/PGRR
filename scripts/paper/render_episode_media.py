#!/usr/bin/env python3
"""Render honest paper media from recorded final-episode telemetry.

The renderer never fabricates a camera view.  It reconstructs a top-down view
from fields already present in an episode JSONL stream and labels every output
``Telemetry reconstruction -- not a camera image``.  A representative episode
can be selected deterministically from ``results.parquet``, or an exact JSONL
stream can be supplied explicitly.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

matplotlib.use("Agg", force=True)


ROOT = Path(__file__).resolve().parents[2]

# Functional colors only: navigation/path, robot/progress, and people/risk.
BLUE = "#315A8A"
TEAL = "#198F8A"
ORANGE = "#D97721"
INK = "#17212B"
MID_GREY = "#66717C"
LIGHT_GREY = "#E4E8EC"
PALE_GREY = "#F6F7F8"

STATE_NAMES = {
    0: "NORMAL",
    1: "PENDING_RECOVERY",
    2: "RECOVERY",
    3: "REJOIN",
    4: "EMERGENCY_STOP",
    5: "FAILED",
    6: "SUCCEEDED",
}
ANGLES_DEGREES = (-90, -60, -30, 0, 30, 60, 90)
RADII_METERS = (0.6, 1.0, 1.4)
CONTINUE_ACTION_ID = 24

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 7,
        "legend.fontsize": 6.5,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


class MediaError(RuntimeError):
    """Raised when recorded evidence is missing or malformed."""


@dataclass(frozen=True, slots=True)
class TelemetryFrame:
    """The small, evidence-preserving subset required for media rendering."""

    timestamp: float
    robot_pose: tuple[float, float, float]
    robot_pose_source: str
    human_positions: tuple[tuple[float, float], ...]
    global_path: tuple[tuple[float, float], ...]
    goal: tuple[float, float] | None
    recovery_state: int
    recovery_action: int
    failure_score: float | None
    distance_to_goal: float | None
    collision: bool
    timeout: bool


@dataclass(frozen=True, slots=True)
class EpisodeTelemetry:
    """Recorded episode plus provenance needed for unambiguous captions."""

    jsonl_path: Path
    episode_id: str
    scenario_id: str
    source_policy: str
    outcome: str
    frames: tuple[TelemetryFrame, ...]


@dataclass(frozen=True, slots=True)
class MediaArtifacts:
    """Paths produced by :func:`render_media`."""

    keyframes_pdf: Path
    keyframes_png: Path
    video_mp4: Path | None


def _root_path(value: Path) -> Path:
    """Resolve CLI paths relative to the repository rather than the shell cwd."""

    return value.expanduser().resolve() if value.is_absolute() else (ROOT / value).resolve()


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _finite_xy(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    x = _finite_number(value[0])
    y = _finite_number(value[1])
    return (x, y) if x is not None and y is not None else None


def _finite_pose(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    components = tuple(_finite_number(component) for component in value[:3])
    if any(component is None for component in components):
        return None
    return components  # type: ignore[return-value]


def _polyline(value: object, *, maximum_points: int = 300) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    points = tuple(point for item in value if (point := _finite_xy(item)) is not None)
    if len(points) <= maximum_points:
        return points
    indices = np.linspace(0, len(points) - 1, maximum_points, dtype=np.int64)
    return tuple(points[int(index)] for index in np.unique(indices))


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MediaError(f"cannot read JSON evidence {path}: {error}") from error
    if not isinstance(payload, dict):
        raise MediaError(f"expected a JSON object in {path}")
    return payload


def _frame_from_record(record: dict[str, Any], *, line_number: int, path: Path) -> TelemetryFrame:
    timestamp = _finite_number(record.get("timestamp"))
    if timestamp is None or timestamp < 0.0:
        raise MediaError(f"invalid timestamp at {path}:{line_number}")

    privileged = record.get("privileged")
    privileged = privileged if isinstance(privileged, dict) else {}
    pose = _finite_pose(privileged.get("robot_pose"))
    pose_source = "privileged simulator pose"
    if pose is None:
        pose = _finite_pose(record.get("robot_pose"))
        pose_source = "logged localized pose"
    if pose is None:
        raise MediaError(f"missing finite robot pose at {path}:{line_number}")

    raw_humans = privileged.get("human_positions")
    humans = (
        tuple(point for item in raw_humans if (point := _finite_xy(item)) is not None)
        if isinstance(raw_humans, (list, tuple))
        else ()
    )
    goal_value = record.get("goal")
    goal = _finite_xy(goal_value)
    try:
        state = int(record.get("recovery_state", 0))
        action = int(record.get("recovery_action", CONTINUE_ACTION_ID))
    except (TypeError, ValueError) as error:
        raise MediaError(f"invalid recovery state/action at {path}:{line_number}") from error
    if not 0 <= action <= CONTINUE_ACTION_ID:
        raise MediaError(f"recovery action outside [0, 24] at {path}:{line_number}")

    return TelemetryFrame(
        timestamp=timestamp,
        robot_pose=pose,
        robot_pose_source=pose_source,
        human_positions=humans,
        global_path=_polyline(record.get("global_path")),
        goal=goal,
        recovery_state=state,
        recovery_action=action,
        failure_score=_finite_number(record.get("failure_score")),
        distance_to_goal=_finite_number(record.get("distance_to_goal")),
        collision=bool(record.get("collision", False)),
        timeout=bool(record.get("timeout", False)),
    )


def load_telemetry(jsonl_path: Path) -> EpisodeTelemetry:
    """Load an exact JSONL stream without deriving or filling missing measurements."""

    path = _root_path(jsonl_path)
    if not path.is_file():
        raise MediaError(f"episode JSONL does not exist: {path}")
    frames: list[TelemetryFrame] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise MediaError(f"invalid JSON at {path}:{line_number}: {error}") from error
                if not isinstance(record, dict):
                    raise MediaError(f"expected a JSON object at {path}:{line_number}")
                frames.append(_frame_from_record(record, line_number=line_number, path=path))
    except OSError as error:
        raise MediaError(f"cannot read episode JSONL {path}: {error}") from error
    if not frames:
        raise MediaError(f"episode JSONL contains no telemetry records: {path}")
    times = np.asarray([frame.timestamp for frame in frames], dtype=np.float64)
    if np.any(np.diff(times) < 0.0):
        raise MediaError(f"episode timestamps are not monotonic: {path}")

    metadata_path = path.with_suffix(".metadata.json")
    metadata = _read_json_object(metadata_path) if metadata_path.is_file() else {}
    outcome_path = path.with_suffix(".outcome.json")
    outcome_payload = _read_json_object(outcome_path) if outcome_path.is_file() else {}
    inferred_outcome = (
        "COLLISION"
        if any(frame.collision for frame in frames)
        else "TIMEOUT"
        if any(frame.timeout for frame in frames)
        else "UNSPECIFIED"
    )
    return EpisodeTelemetry(
        jsonl_path=path,
        episode_id=str(metadata.get("episode_id") or path.stem),
        scenario_id=str(metadata.get("scenario_id") or "unspecified"),
        source_policy=str(metadata.get("source_policy") or "unspecified"),
        outcome=str(outcome_payload.get("outcome") or inferred_outcome),
        frames=tuple(frames),
    )


def _truthy_series(series: pd.Series[Any]) -> pd.Series[bool]:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes"})


def select_representative(
    results_path: Path,
    raw_dir: Path,
    *,
    method: str = "bc",
    episode_id: str | None = None,
) -> Path:
    """Select one recorded stream with a fixed, documented ordering.

    The preference classes are: successful recovery-triggered episode, any
    recovery-triggered episode, any successful episode, and then any remaining
    valid episode.  Within a class, high density precedes medium and low,
    followed by descending trigger count and lexical scenario/episode IDs.
    This is evidence selection for visualization only, never metric filtering.
    """

    results = _root_path(results_path)
    raw = _root_path(raw_dir)
    if not results.is_file():
        raise MediaError(
            "final results are unavailable: "
            f"{results}. Run the final collector first or pass --jsonl explicitly."
        )
    try:
        frame = pd.read_parquet(results)
    except Exception as error:
        raise MediaError(f"cannot read final results {results}: {error}") from error
    if frame.empty:
        raise MediaError(f"final results contain no episodes: {results}")
    if "episode_id" not in frame.columns:
        raise MediaError(f"final results lack required column 'episode_id': {results}")

    policy_column = "source_policy" if "source_policy" in frame.columns else "method"
    if policy_column not in frame.columns:
        raise MediaError(f"final results lack source_policy/method: {results}")
    candidates = frame[frame[policy_column].astype(str) == method].copy()
    if episode_id is not None:
        candidates = candidates[candidates["episode_id"].astype(str) == episode_id]
    if "included_in_algorithm_metrics" in candidates.columns:
        candidates = candidates[_truthy_series(candidates["included_in_algorithm_metrics"])]
    if candidates.empty:
        available = sorted(frame[policy_column].dropna().astype(str).unique())
        detail = f" and episode_id={episode_id!r}" if episode_id is not None else ""
        raise MediaError(
            f"no valid result for method={method!r}{detail}; available methods={available}"
        )

    candidates["_jsonl"] = candidates["episode_id"].map(lambda value: raw / f"{value!s}.jsonl")
    candidates = candidates[candidates["_jsonl"].map(Path.is_file)].copy()
    if candidates.empty:
        raise MediaError(
            f"valid result rows exist for method={method!r}, but no matching JSONL exists in {raw}"
        )

    outcome = candidates.get("outcome", pd.Series("", index=candidates.index)).astype(str)
    trigger = pd.to_numeric(
        candidates.get("recovery_trigger_count", pd.Series(0, index=candidates.index)),
        errors="coerce",
    ).fillna(0.0)
    success = outcome.eq("GOAL_REACHED")
    candidates["_selection_class"] = np.select(
        [success & trigger.gt(0), trigger.gt(0), success],
        [0, 1, 2],
        default=3,
    )
    density = candidates.get("density", pd.Series("", index=candidates.index)).astype(str)
    candidates["_density_rank"] = density.map({"high": 0, "medium": 1, "low": 2}).fillna(3)
    candidates["_trigger_rank"] = -trigger
    candidates["_family_rank"] = candidates.get(
        "family", candidates.get("scenario_id", pd.Series("", index=candidates.index))
    ).astype(str)
    candidates["_seed_rank"] = pd.to_numeric(
        candidates.get("seed", pd.Series(0, index=candidates.index)), errors="coerce"
    ).fillna(0)
    ordered = candidates.sort_values(
        [
            "_selection_class",
            "_density_rank",
            "_trigger_rank",
            "_family_rank",
            "_seed_rank",
            "episode_id",
        ],
        kind="mergesort",
    )
    return Path(ordered.iloc[0]["_jsonl"])


def action_label(action_id: int) -> str:
    """Return the fixed 25-action label used by the deployed policy."""

    if 0 <= action_id < 21:
        radius = RADII_METERS[action_id // len(ANGLES_DEGREES)]
        angle = ANGLES_DEGREES[action_id % len(ANGLES_DEGREES)]
        return f"SUBGOAL {radius:.1f} m / {angle:+d} deg"
    return {21: "WAIT", 22: "BACKUP", 23: "REPLAN", 24: "CONTINUE"}.get(
        action_id, f"ACTION {action_id}"
    )


def keyframe_indices(frames: tuple[TelemetryFrame, ...], count: int = 4) -> tuple[int, ...]:
    """Choose start, first intervention, peak score, and terminal evidence frames."""

    if count <= 0:
        raise ValueError("keyframe count must be positive")
    last = len(frames) - 1
    intervention = next(
        (
            index
            for index, frame in enumerate(frames)
            if frame.recovery_state != 0 or frame.recovery_action != CONTINUE_ACTION_ID
        ),
        0,
    )
    finite_scores = [
        (frame.failure_score, index)
        for index, frame in enumerate(frames)
        if frame.failure_score is not None
    ]
    peak = max(finite_scores, default=(0.0, intervention), key=lambda item: (item[0], -item[1]))[1]
    preferred = [0, intervention, peak, last]
    candidates = preferred + np.linspace(0, last, max(count * 2, 2), dtype=np.int64).tolist()
    selected: list[int] = []
    for value in candidates:
        index = int(value)
        if index not in selected:
            selected.append(index)
        if len(selected) == min(count, len(frames)):
            break
    return tuple(sorted(selected))


def _video_indices(frames: tuple[TelemetryFrame, ...], maximum_frames: int) -> tuple[int, ...]:
    if maximum_frames <= 0:
        raise ValueError("maximum_frames must be positive")
    if len(frames) <= maximum_frames:
        return tuple(range(len(frames)))
    base = set(np.linspace(0, len(frames) - 1, maximum_frames, dtype=np.int64).tolist())
    events = {
        index
        for index in range(1, len(frames))
        if frames[index].recovery_state != frames[index - 1].recovery_state
        or frames[index].recovery_action != frames[index - 1].recovery_action
    }
    events.update({0, len(frames) - 1})
    combined = sorted(base | events)
    if len(combined) <= maximum_frames:
        return tuple(combined)
    # Preserve all possible transition evidence, then fill remaining slots uniformly.
    ordered_events = sorted(events)
    if len(ordered_events) >= maximum_frames:
        indices = np.linspace(0, len(ordered_events) - 1, maximum_frames, dtype=np.int64)
        return tuple(ordered_events[int(index)] for index in np.unique(indices))
    remaining = [index for index in combined if index not in events]
    slots = maximum_frames - len(ordered_events)
    fill_indices = np.linspace(0, len(remaining) - 1, slots, dtype=np.int64)
    return tuple(sorted(ordered_events + [remaining[int(index)] for index in fill_indices]))


def _world_bounds(episode: EpisodeTelemetry) -> tuple[float, float, float, float]:
    coordinates: list[tuple[float, float]] = [frame.robot_pose[:2] for frame in episode.frames]
    for frame in episode.frames:
        coordinates.extend(frame.human_positions)
        coordinates.extend(frame.global_path)
        if frame.goal is not None:
            coordinates.append(frame.goal)
    values = np.asarray(coordinates, dtype=np.float64)
    x_min, y_min = np.min(values, axis=0)
    x_max, y_max = np.max(values, axis=0)
    x_span = max(float(x_max - x_min), 2.0)
    y_span = max(float(y_max - y_min), 2.0)
    margin = 0.08 * max(x_span, y_span) + 0.25
    return (
        float(x_min - margin),
        float(x_max + margin),
        float(y_min - margin),
        float(y_max + margin),
    )


def _state_name(value: int) -> str:
    return STATE_NAMES.get(value, f"STATE_{value}")


def _draw_map(
    axis: Axes,
    episode: EpisodeTelemetry,
    index: int,
    bounds: tuple[float, float, float, float],
    *,
    show_legend: bool,
) -> None:
    frame = episode.frames[index]
    trajectory = np.asarray([item.robot_pose[:2] for item in episode.frames], dtype=np.float64)
    if frame.global_path:
        path = np.asarray(frame.global_path, dtype=np.float64)
        axis.plot(
            path[:, 0],
            path[:, 1],
            color=BLUE,
            linewidth=1.0,
            alpha=0.7,
            label="logged global path",
            zorder=1,
        )
    else:
        axis.text(
            0.98,
            0.03,
            "global path unavailable at this sample",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize=5.4,
            color=MID_GREY,
        )
    axis.plot(
        trajectory[: index + 1, 0],
        trajectory[: index + 1, 1],
        color=TEAL,
        linewidth=1.4,
        label="recorded robot trail",
        zorder=2,
    )
    if frame.human_positions:
        humans = np.asarray(frame.human_positions, dtype=np.float64)
        axis.scatter(
            humans[:, 0],
            humans[:, 1],
            color=ORANGE,
            edgecolor="white",
            linewidth=0.45,
            s=35,
            label="logged human positions",
            zorder=5,
        )
    pose = frame.robot_pose
    axis.scatter(
        [pose[0]],
        [pose[1]],
        color=TEAL,
        edgecolor="white",
        linewidth=0.55,
        s=50,
        zorder=7,
    )
    heading = 0.045 * max(bounds[1] - bounds[0], bounds[3] - bounds[2])
    axis.annotate(
        "",
        xy=(pose[0] + heading * math.cos(pose[2]), pose[1] + heading * math.sin(pose[2])),
        xytext=(pose[0], pose[1]),
        arrowprops={"arrowstyle": "-|>", "color": TEAL, "lw": 1.1},
        zorder=8,
    )
    if frame.goal is not None:
        axis.scatter(
            [frame.goal[0]],
            [frame.goal[1]],
            marker="*",
            color=BLUE,
            edgecolor="white",
            linewidth=0.35,
            s=75,
            label="logged goal",
            zorder=6,
        )
    axis.set_xlim(bounds[0], bounds[1])
    axis.set_ylim(bounds[2], bounds[3])
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("world x [m]")
    axis.set_ylabel("world y [m]")
    axis.grid(color=LIGHT_GREY, linewidth=0.5)
    axis.set_axisbelow(True)
    if show_legend:
        axis.legend(loc="upper left", frameon=False, ncols=2)


def _source_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _render_keyframes(
    episode: EpisodeTelemetry,
    pdf_path: Path,
    png_path: Path,
    *,
    count: int,
) -> None:
    selected = keyframe_indices(episode.frames, count=count)
    bounds = _world_bounds(episode)
    columns = 2
    rows = math.ceil(len(selected) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(7.15, 3.35 * rows),
        squeeze=False,
        constrained_layout=False,
    )
    labels = "abcdefghijklmnopqrstuvwxyz"
    for panel, (axis, index) in enumerate(zip(axes.flat, selected, strict=False)):
        frame = episode.frames[index]
        _draw_map(axis, episode, index, bounds, show_legend=panel == 0)
        axis.set_title(
            f"({labels[panel]}) t={frame.timestamp:.1f} s | "
            f"{_state_name(frame.recovery_state)} | {action_label(frame.recovery_action)}",
            loc="left",
            fontweight="bold",
        )
    for axis in list(axes.flat)[len(selected) :]:
        axis.set_visible(False)
    figure.suptitle(
        f"Telemetry reconstruction — {episode.episode_id}\n"
        f"{episode.scenario_id} | {episode.source_policy} | {episode.outcome}",
        fontsize=9,
        fontweight="bold",
        y=0.995,
    )
    pose_sources = ", ".join(sorted({frame.robot_pose_source for frame in episode.frames}))
    human_note = (
        "privileged simulator human positions"
        if any(frame.human_positions for frame in episode.frames)
        else "human positions unavailable"
    )
    figure.text(
        0.5,
        0.006,
        "Telemetry reconstruction — not a camera image. "
        f"Pose: {pose_sources}; people: {human_note}. Source: {_source_label(episode.jsonl_path)}",
        ha="center",
        va="bottom",
        fontsize=5.7,
        color=MID_GREY,
    )
    figure.subplots_adjust(left=0.08, right=0.985, top=0.91, bottom=0.06, wspace=0.20, hspace=0.25)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=220, bbox_inches="tight")
    plt.close(figure)


def _state_trace(axis: Axes, episode: EpisodeTelemetry, index: int) -> None:
    time = np.asarray([frame.timestamp for frame in episode.frames], dtype=np.float64)
    state = np.asarray([frame.recovery_state for frame in episode.frames], dtype=np.float64)
    axis.step(time, state, where="post", color=BLUE, linewidth=0.8)
    axis.axvline(episode.frames[index].timestamp, color=ORANGE, linewidth=1.0)
    present = sorted(set(state.astype(int)))
    axis.set_yticks(present, [_state_name(value) for value in present])
    axis.set_xlabel("simulation time [s]")
    axis.set_ylabel("state")
    axis.grid(axis="y", color=LIGHT_GREY, linewidth=0.45)
    axis.set_axisbelow(True)


def _video_figure() -> tuple[Figure, Axes, Axes, Axes]:
    figure = plt.figure(figsize=(8.0, 5.0), constrained_layout=False)
    grid = figure.add_gridspec(
        2,
        2,
        left=0.075,
        right=0.98,
        top=0.87,
        bottom=0.12,
        width_ratios=(4.4, 1.55),
        height_ratios=(4.5, 1.0),
        wspace=0.18,
        hspace=0.30,
    )
    map_axis = figure.add_subplot(grid[0, 0])
    info_axis = figure.add_subplot(grid[0, 1])
    timeline_axis = figure.add_subplot(grid[1, :])
    return figure, map_axis, info_axis, timeline_axis


def _draw_video_frame(
    figure: Figure,
    map_axis: Axes,
    info_axis: Axes,
    timeline_axis: Axes,
    episode: EpisodeTelemetry,
    index: int,
    bounds: tuple[float, float, float, float],
) -> None:
    map_axis.clear()
    info_axis.clear()
    timeline_axis.clear()
    frame = episode.frames[index]
    _draw_map(map_axis, episode, index, bounds, show_legend=True)
    info_axis.set_facecolor(PALE_GREY)
    info_axis.set_xticks([])
    info_axis.set_yticks([])
    for spine in info_axis.spines.values():
        spine.set_color(LIGHT_GREY)
    score = "unavailable" if frame.failure_score is None else f"{frame.failure_score:.3f}"
    distance = (
        "unavailable" if frame.distance_to_goal is None else f"{frame.distance_to_goal:.2f} m"
    )
    people = str(len(frame.human_positions)) if frame.human_positions else "unavailable"
    info_axis.text(
        0.06,
        0.95,
        f"t = {frame.timestamp:.1f} s\n\n"
        f"State\n{_state_name(frame.recovery_state)}\n\n"
        f"Action\n{action_label(frame.recovery_action)}\n\n"
        f"Failure score\n{score}\n\n"
        f"Goal distance\n{distance}\n\n"
        f"Logged people\n{people}",
        transform=info_axis.transAxes,
        ha="left",
        va="top",
        fontsize=7,
        color=INK,
        linespacing=1.2,
    )
    _state_trace(timeline_axis, episode, index)
    figure.suptitle(
        "Telemetry reconstruction — not a camera image\n"
        f"{episode.episode_id} | {episode.scenario_id} | "
        f"{episode.source_policy} | {episode.outcome}",
        fontsize=9,
        fontweight="bold",
        color=INK,
    )
    figure.text(
        0.5,
        0.025,
        "Top-down view reconstructed only from logged robot pose, human positions, "
        "global path, recovery state, and action.",
        ha="center",
        color=MID_GREY,
        fontsize=6,
    )


def ffmpeg_executable() -> Path | None:
    """Return a usable system or packaged ffmpeg without downloading anything."""

    system = shutil.which("ffmpeg")
    if system is not None:
        return Path(system)
    try:
        import imageio_ffmpeg

        packaged = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError, OSError):
        return None
    return packaged if packaged.is_file() and os.access(packaged, os.X_OK) else None


def _render_video(
    episode: EpisodeTelemetry,
    destination: Path,
    *,
    fps: int,
    maximum_frames: int,
    ffmpeg: Path,
) -> None:
    try:
        import imageio.v2 as imageio
    except ImportError as error:
        raise MediaError("imageio is required to encode MP4 evidence") from error
    if fps <= 0:
        raise ValueError("fps must be positive")
    indices = _video_indices(episode.frames, maximum_frames)
    bounds = _world_bounds(episode)
    figure, map_axis, info_axis, timeline_axis = _video_figure()
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous_ffmpeg = os.environ.get("IMAGEIO_FFMPEG_EXE")
    os.environ["IMAGEIO_FFMPEG_EXE"] = str(ffmpeg)
    try:
        with imageio.get_writer(
            destination,
            format="FFMPEG",
            mode="I",
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=2,
            ffmpeg_log_level="error",
            output_params=["-metadata", "comment=Telemetry reconstruction; not a camera image"],
        ) as writer:
            for index in indices:
                _draw_video_frame(
                    figure,
                    map_axis,
                    info_axis,
                    timeline_axis,
                    episode,
                    index,
                    bounds,
                )
                figure.canvas.draw()
                rgba = np.asarray(figure.canvas.buffer_rgba())
                writer.append_data(rgba[:, :, :3])
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise MediaError(f"failed to encode telemetry MP4 {destination}: {error}") from error
    finally:
        plt.close(figure)
        if previous_ffmpeg is None:
            os.environ.pop("IMAGEIO_FFMPEG_EXE", None)
        else:
            os.environ["IMAGEIO_FFMPEG_EXE"] = previous_ffmpeg


def render_media(
    episode: EpisodeTelemetry,
    *,
    figure_dir: Path,
    video_dir: Path,
    keyframe_count: int = 4,
    fps: int = 10,
    maximum_video_frames: int = 240,
    make_video: bool = True,
) -> MediaArtifacts:
    """Create PDF/PNG keyframes and, when available, an MP4 reconstruction."""

    safe_id = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in episode.episode_id
    )
    figure_directory = _root_path(figure_dir)
    video_directory = _root_path(video_dir)
    pdf = figure_directory / f"{safe_id}_telemetry_keyframes.pdf"
    png = figure_directory / f"{safe_id}_telemetry_keyframes.png"
    _render_keyframes(episode, pdf, png, count=keyframe_count)

    video: Path | None = None
    if make_video:
        ffmpeg = ffmpeg_executable()
        if ffmpeg is None:
            print(
                "warning: ffmpeg unavailable; PDF/PNG generated but MP4 skipped",
                file=sys.stderr,
            )
        else:
            video = video_directory / f"{safe_id}_telemetry.mp4"
            _render_video(
                episode,
                video,
                fps=fps,
                maximum_frames=maximum_video_frames,
                ffmpeg=ffmpeg,
            )
    return MediaArtifacts(pdf, png, video)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--results",
        type=Path,
        help="final results.parquet; defaults to outputs/final/results.parquet",
    )
    source.add_argument("--jsonl", type=Path, help="render this exact recorded JSONL stream")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--method", default="bc", help="policy selected from results.parquet")
    parser.add_argument("--episode-id", help="optional exact episode ID within results.parquet")
    parser.add_argument("--figure-dir", type=Path, default=Path("outputs/figures"))
    parser.add_argument("--video-dir", type=Path, default=Path("outputs/videos"))
    parser.add_argument("--keyframes", type=int, default=4)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--max-video-frames", type=int, default=240)
    parser.add_argument("--skip-video", action="store_true", help="generate only PDF/PNG")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.keyframes <= 0:
        parser.error("--keyframes must be positive")
    if args.fps <= 0:
        parser.error("--fps must be positive")
    if args.max_video_frames <= 0:
        parser.error("--max-video-frames must be positive")
    if args.jsonl is not None and args.episode_id is not None:
        parser.error("--episode-id is only valid with --results")

    try:
        if args.jsonl is not None:
            jsonl = args.jsonl
            selection = "explicit --jsonl"
        else:
            results = args.results or Path("outputs/final/results.parquet")
            jsonl = select_representative(
                results,
                args.raw_dir,
                method=args.method,
                episode_id=args.episode_id,
            )
            selection = (
                "fixed order: successful+triggered, triggered, successful, other; "
                "then density, trigger count, scenario, seed, episode ID"
            )
        episode = load_telemetry(jsonl)
        artifacts = render_media(
            episode,
            figure_dir=args.figure_dir,
            video_dir=args.video_dir,
            keyframe_count=args.keyframes,
            fps=args.fps,
            maximum_video_frames=args.max_video_frames,
            make_video=not args.skip_video,
        )
    except MediaError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"episode: {episode.episode_id}")
    print(f"selection: {selection}")
    print(f"source: {episode.jsonl_path}")
    print(f"keyframes PDF: {artifacts.keyframes_pdf}")
    print(f"keyframes PNG: {artifacts.keyframes_png}")
    print(f"MP4: {artifacts.video_mp4 if artifacts.video_mp4 is not None else 'skipped'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
