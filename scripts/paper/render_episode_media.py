#!/usr/bin/env python3
"""Render honest paper media from recorded final-episode telemetry.

The renderer never fabricates a camera view.  It reconstructs a top-down view
from fields already present in an episode JSONL stream and labels every output
``Telemetry reconstruction -- not a camera image``.  A representative episode
can be selected deterministically from ``results.parquet``, or an exact JSONL
stream can be supplied explicitly.  ``--matched-final`` is the stricter paper
path: it accepts only the complete locked moderate test, verifies result/raw/
sidecar/scenario SHA-256 bindings, and renders a same-``pair_id`` Base--PGRR
trajectory plus the corresponding measured PGRR recovery timeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon

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

# Locked moderate-publication protocol.  Keeping these constraints local makes
# this renderer independently fail closed: it cannot silently turn a partial,
# validation, or historical table into publication media.
PUBLICATION_METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
PUBLICATION_FAMILIES = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)
PUBLICATION_DENSITIES = ("low", "medium", "high")
PUBLICATION_REPLICATES_PER_CELL = 5
PUBLICATION_CONDITION_COUNT = (
    len(PUBLICATION_FAMILIES) * len(PUBLICATION_DENSITIES) * PUBLICATION_REPLICATES_PER_CELL
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
ALGORITHM_OUTCOMES = {"GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE"}
EXCLUDED_OUTCOMES = {"SIMULATOR_FAILURE", "INVALID_RESET"}
KNOWN_OUTCOMES = ALGORITHM_OUTCOMES | EXCLUDED_OUTCOMES
PAIR_INVARIANT_COLUMNS = (
    "scenario_id",
    "family",
    "density",
    "seed",
    "split",
    "replicate",
    "scenario_path",
    "scenario_sha256",
    "project_commit",
)
FORBIDDEN_PUBLICATION_TOKENS = re.compile(r"(?:validation|historical)", re.IGNORECASE)

MATCHED_TRAJECTORY_NAME = "moderate_matched_base_pgrr_trajectory.pdf"
PGRR_TIMELINE_NAME = "moderate_pgrr_recovery_timeline.pdf"
TELEMETRY_NOTICE = "Telemetry reconstruction—not a camera image"

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
    odometry_pose: tuple[float, float, float] | None
    human_positions: tuple[tuple[float, float], ...]
    global_path: tuple[tuple[float, float], ...]
    goal: tuple[float, float] | None
    recovery_state: int
    recovery_action: int
    failure_score: float | None
    distance_to_goal: float | None
    collision: bool
    timeout: bool
    recovery_reason: str


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


@dataclass(frozen=True, slots=True)
class ScenarioEvidence:
    """SHA-bound configured geometry shared by one matched condition."""

    path: Path
    scenario_id: str
    family: str
    density: str
    seed: int
    robot_start: tuple[float, float]
    robot_goal: tuple[float, float]
    static_boxes: tuple[tuple[float, float, float, float, float], ...]
    actor_routes: tuple[tuple[tuple[float, float], ...], ...]


@dataclass(frozen=True, slots=True)
class MatchedEpisodeEvidence:
    """One immutable Base--PGRR condition selected for descriptive media."""

    pair_id: str
    base_row: Mapping[str, Any]
    pgrr_row: Mapping[str, Any]
    base: EpisodeTelemetry
    pgrr: EpisodeTelemetry
    scenario: ScenarioEvidence
    selection_rule: str


@dataclass(frozen=True, slots=True)
class MatchedMediaArtifacts:
    """Publication PDFs generated from a SHA-verified matched test pair."""

    trajectory_pdf: Path
    timeline_pdf: Path


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
    odometry_pose = _finite_pose(record.get("robot_pose"))
    pose = _finite_pose(privileged.get("robot_pose"))
    pose_source = "privileged simulator pose"
    if pose is None:
        pose = odometry_pose
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
    if state not in STATE_NAMES:
        raise MediaError(f"unknown recovery state {state} at {path}:{line_number}")
    recovery_reason = record.get("recovery_reason", "")
    if not isinstance(recovery_reason, str):
        raise MediaError(f"invalid recovery reason at {path}:{line_number}")

    return TelemetryFrame(
        timestamp=timestamp,
        robot_pose=pose,
        robot_pose_source=pose_source,
        odometry_pose=odometry_pose,
        human_positions=humans,
        global_path=_polyline(record.get("global_path")),
        goal=goal,
        recovery_state=state,
        recovery_action=action,
        failure_score=_finite_number(record.get("failure_score")),
        distance_to_goal=_finite_number(record.get("distance_to_goal")),
        collision=bool(record.get("collision", False)),
        timeout=bool(record.get("timeout", False)),
        recovery_reason=recovery_reason.strip(),
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise MediaError(f"cannot hash evidence {path}: {error}") from error
    return digest.hexdigest()


def _require_result_columns(frame: pd.DataFrame, columns: Sequence[str], path: Path) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise MediaError(f"complete test results {path} lack columns: {', '.join(missing)}")


def _metadata_token(value: object) -> str:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    try:
        if bool(pd.isna(value)):
            return "<NULL>"
    except (TypeError, ValueError):
        pass
    return str(value)


def load_complete_moderate_test_results(results_path: Path) -> pd.DataFrame:
    """Load the locked 600-row test table or reject it without rendering.

    This check intentionally duplicates the publication-critical subset of the
    statistics validator.  Media generation is often invoked independently of
    the paper build, so it must not rely on an earlier process having rejected
    validation data, partial method coverage, or mismatched pairs.
    """

    path = _root_path(results_path)
    if not path.is_file():
        raise MediaError(
            "complete moderate test results are unavailable: "
            f"{path}. Expected outputs/moderate/final/results.parquet."
        )
    try:
        frame = pd.read_parquet(path)
    except Exception as error:
        raise MediaError(f"cannot read complete test results {path}: {error}") from error
    required = (
        "episode_id",
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "seed",
        "replicate",
        "split",
        "source_policy",
        "outcome",
        "included_in_algorithm_metrics",
        "project_commit",
        "recovery_trigger_count",
        "raw_sha256",
        "metadata_sha256",
        "outcome_sha256",
        "scenario_path",
        "scenario_sha256",
    )
    _require_result_columns(frame, required, path)
    if frame.empty:
        raise MediaError(f"complete test results contain no rows: {path}")
    results = frame.copy()
    string_columns = (
        "episode_id",
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "split",
        "source_policy",
        "outcome",
        "project_commit",
        "raw_sha256",
        "metadata_sha256",
        "outcome_sha256",
        "scenario_path",
        "scenario_sha256",
    )
    for column in string_columns:
        if bool(results[column].isna().any()):
            raise MediaError(f"complete test results contain null {column}: {path}")
        results[column] = results[column].astype(str).str.strip()
        if bool(results[column].eq("").any()):
            raise MediaError(f"complete test results contain empty {column}: {path}")

    results["split"] = results["split"].str.lower()
    observed_splits = sorted(set(results["split"]))
    if observed_splits != ["test"]:
        raise MediaError(
            f"publication media require exactly the locked test split; observed={observed_splits}"
        )
    for column in ("episode_id", "pair_id", "scenario_id", "scenario_path"):
        rejected = results[column].str.contains(FORBIDDEN_PUBLICATION_TOKENS, na=False)
        if bool(rejected.any()):
            value = str(results.loc[rejected, column].iloc[0])
            raise MediaError(
                f"publication media reject validation/historical evidence: {column}={value!r}"
            )

    results["outcome"] = results["outcome"].str.upper().str.replace(" ", "_", regex=False)
    unknown = sorted(set(results["outcome"]) - KNOWN_OUTCOMES)
    if unknown:
        raise MediaError(f"complete test results contain unknown outcomes: {unknown}")
    included = _truthy_series(results["included_in_algorithm_metrics"])
    expected_included = ~results["outcome"].isin(EXCLUDED_OUTCOMES)
    if not bool((included == expected_included).all()):
        raise MediaError("included_in_algorithm_metrics disagrees with outcome semantics")
    results["included_in_algorithm_metrics"] = included

    observed_methods = set(results["source_policy"])
    if observed_methods != set(PUBLICATION_METHODS):
        raise MediaError(
            "complete test results require exactly the five registered methods; "
            f"missing={sorted(set(PUBLICATION_METHODS) - observed_methods)}, "
            f"extra={sorted(observed_methods - set(PUBLICATION_METHODS))}"
        )
    expected_rows = PUBLICATION_CONDITION_COUNT * len(PUBLICATION_METHODS)
    if len(results) != expected_rows:
        raise MediaError(
            f"complete test results require {expected_rows} rows; observed={len(results)}"
        )
    if int(results["pair_id"].nunique()) != PUBLICATION_CONDITION_COUNT:
        raise MediaError(
            f"complete test results require {PUBLICATION_CONDITION_COUNT} immutable pair_id values"
        )
    if bool(results["episode_id"].duplicated(keep=False).any()):
        duplicate = str(results.loc[results["episode_id"].duplicated(), "episode_id"].iloc[0])
        raise MediaError(f"episode_id values are not unique: {duplicate}")
    if bool(results.duplicated(["pair_id", "source_policy"], keep=False).any()):
        raise MediaError("complete test results contain duplicate pair_id/method rows")

    commits = sorted(set(results["project_commit"].str.lower()))
    if len(commits) != 1 or COMMIT_PATTERN.fullmatch(commits[0]) is None:
        raise MediaError("publication media require one uniform 40-hex project_commit")
    results["project_commit"] = commits[0]
    for column in ("raw_sha256", "metadata_sha256", "outcome_sha256", "scenario_sha256"):
        invalid = ~results[column].str.lower().map(
            lambda value: SHA256_PATTERN.fullmatch(value) is not None
        )
        if bool(invalid.any()):
            episode = str(results.loc[invalid, "episode_id"].iloc[0])
            raise MediaError(f"{column} is not a 64-hex digest for episode {episode}")
        results[column] = results[column].str.lower()

    families = set(results["family"])
    densities = set(results["density"])
    if families != set(PUBLICATION_FAMILIES):
        raise MediaError(
            "complete test results require the eight registered families; "
            f"missing={sorted(set(PUBLICATION_FAMILIES) - families)}, "
            f"extra={sorted(families - set(PUBLICATION_FAMILIES))}"
        )
    if densities != set(PUBLICATION_DENSITIES):
        raise MediaError(
            f"complete test results require low/medium/high density; observed={sorted(densities)}"
        )
    for column in ("seed", "replicate", "recovery_trigger_count"):
        values = pd.to_numeric(results[column], errors="coerce")
        if not bool(np.isfinite(values.to_numpy(dtype=float)).all()):
            raise MediaError(f"complete test results contain non-finite {column}")
        results[column] = values
    if bool((results["recovery_trigger_count"] < 0.0).any()):
        raise MediaError("complete test results contain negative recovery_trigger_count")

    for pair_id, group in results.groupby("pair_id", sort=False, dropna=False):
        if len(group) != len(PUBLICATION_METHODS) or set(group["source_policy"]) != set(
            PUBLICATION_METHODS
        ):
            raise MediaError(f"pair_id={pair_id!r} does not contain all five methods exactly once")
        for column in PAIR_INVARIANT_COLUMNS:
            tokens = group[column].map(_metadata_token)
            if int(tokens.nunique(dropna=False)) != 1:
                raise MediaError(f"pair metadata mismatch: pair_id={pair_id!r}, column={column}")

    conditions = results.drop_duplicates("pair_id")
    cell_counts = conditions.groupby(["family", "density"], observed=True).size()
    if len(cell_counts) != len(PUBLICATION_FAMILIES) * len(PUBLICATION_DENSITIES) or not bool(
        (cell_counts == PUBLICATION_REPLICATES_PER_CELL).all()
    ):
        raise MediaError(
            "complete test results require five immutable conditions per family/density cell"
        )
    replicates = conditions.groupby(["family", "density"], observed=True)["replicate"].apply(
        lambda values: set(int(value) for value in values)
    )
    expected_replicates = set(range(PUBLICATION_REPLICATES_PER_CELL))
    if not bool(replicates.map(lambda values: values == expected_replicates).all()):
        raise MediaError(
            "complete test results require replicates 0..4 in every family/density cell"
        )
    return results


def _safe_episode_stream(raw_dir: Path, episode_id: object) -> Path:
    identifier = str(episode_id)
    if Path(identifier).name != identifier or not identifier:
        raise MediaError(f"unsafe episode_id in complete test results: {identifier!r}")
    return _root_path(raw_dir) / f"{identifier}.jsonl"


def _verify_digest(path: Path, declared: object, label: str) -> str:
    digest = str(declared).strip().lower()
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise MediaError(f"invalid declared {label} SHA-256 for {path.name}: {digest!r}")
    if not path.is_file():
        raise MediaError(f"missing SHA-bound {label} evidence: {path}")
    actual = _sha256(path)
    if actual != digest:
        raise MediaError(f"{label} SHA-256 mismatch for {path}: declared={digest}, actual={actual}")
    return actual


def _read_bound_json(path: Path, declared: object, label: str) -> dict[str, Any]:
    _verify_digest(path, declared, label)
    return _read_json_object(path)


def _verify_selected_episode(row: Mapping[str, Any], raw_dir: Path) -> EpisodeTelemetry:
    episode_id = str(row["episode_id"])
    stream = _safe_episode_stream(raw_dir, episode_id)
    _verify_digest(stream, row["raw_sha256"], "raw JSONL")
    metadata_path = stream.with_suffix(".metadata.json")
    outcome_path = stream.with_suffix(".outcome.json")
    metadata = _read_bound_json(metadata_path, row["metadata_sha256"], "metadata")
    outcome = _read_bound_json(outcome_path, row["outcome_sha256"], "outcome")
    expected_metadata = {
        "episode_id": episode_id,
        "scenario_id": str(row["scenario_id"]),
        "split": "test",
        "source_policy": str(row["source_policy"]),
        "project_commit": str(row["project_commit"]),
    }
    for key, expected in expected_metadata.items():
        if str(metadata.get(key, "")) != expected:
            raise MediaError(
                f"SHA-bound metadata mismatch for {episode_id}: "
                f"{key}={metadata.get(key)!r}, expected={expected!r}"
            )
    try:
        metadata_seed = int(str(metadata.get("seed", "")))
    except (TypeError, ValueError) as error:
        raise MediaError(f"SHA-bound metadata lacks an integer seed: {episode_id}") from error
    if metadata_seed != int(row["seed"]):
        raise MediaError(f"SHA-bound metadata seed mismatch for {episode_id}")
    declared_outcome = str(row["outcome"])
    if str(outcome.get("episode_id", "")) != episode_id:
        raise MediaError(f"SHA-bound outcome sidecar identifies another episode: {episode_id}")
    if str(outcome.get("outcome", "")).upper() != declared_outcome:
        raise MediaError(f"SHA-bound outcome disagrees with results for {episode_id}")

    episode = load_telemetry(stream)
    if episode.episode_id != episode_id or episode.outcome.upper() != declared_outcome:
        raise MediaError(f"loaded telemetry provenance disagrees with results for {episode_id}")
    if len(episode.frames) < 3:
        raise MediaError(f"publication telemetry requires at least three frames: {stream}")
    times = np.asarray([frame.timestamp for frame in episode.frames], dtype=np.float64)
    if bool(np.any(np.diff(times) <= 0.0)):
        raise MediaError(f"publication telemetry timestamps must be strictly increasing: {stream}")
    if any(frame.odometry_pose is None for frame in episode.frames):
        raise MediaError(f"publication telemetry lacks a logged odometry pose: {stream}")
    if "sample_count" in outcome:
        try:
            outcome_sample_count = int(str(outcome["sample_count"]))
        except ValueError as error:
            raise MediaError(f"outcome has invalid sample_count for {episode_id}") from error
        if outcome_sample_count != len(episode.frames):
            raise MediaError(f"outcome sample_count disagrees with raw JSONL for {episode_id}")
    if "sample_count" in row and not pd.isna(row["sample_count"]):
        if int(row["sample_count"]) != len(episode.frames):
            raise MediaError(f"results sample_count disagrees with raw JSONL for {episode_id}")
    return episode


def _scenario_path(value: object, scenario_root: Path) -> Path:
    raw = Path(str(value)).expanduser()
    return raw.resolve() if raw.is_absolute() else (_root_path(scenario_root) / raw).resolve()


def _shelf_box(obstacle: Mapping[str, Any], path: Path) -> tuple[float, float, float, float, float]:
    if obstacle.get("model") != "shelf":
        raise MediaError(f"unsupported static geometry in {path}: {obstacle.get('model')!r}")
    position = obstacle.get("pos")
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise MediaError(f"static shelf lacks a finite pose in {path}")
    x = _finite_number(position[0])
    y = _finite_number(position[1])
    yaw = _finite_number(position[2]) if len(position) > 2 else 0.0
    if x is None or y is None or yaw is None:
        raise MediaError(f"static shelf lacks a finite pose in {path}")
    # Exact shelf_static.sdf footprint used by ramp_core.geometry at runtime:
    # local x +/-0.45, local y [-0.395, 0.005].
    center_x = x + 0.195 * math.sin(yaw)
    center_y = y - 0.195 * math.cos(yaw)
    return center_x, center_y, 0.45, 0.20, yaw


def load_scenario_evidence(row: Mapping[str, Any], scenario_root: Path) -> ScenarioEvidence:
    """Load SHA-verified configured geometry for one publication condition."""

    path = _scenario_path(row["scenario_path"], scenario_root)
    _verify_digest(path, row["scenario_sha256"], "scenario")
    payload = _read_json_object(path)
    metadata = payload.get("ramp_metadata")
    if not isinstance(metadata, dict):
        raise MediaError(f"scenario lacks ramp_metadata: {path}")
    expected = {
        "scenario_id": str(row["scenario_id"]),
        "family": str(row["family"]),
        "density": str(row["density"]),
        "split": "test",
    }
    for key, value in expected.items():
        if str(metadata.get(key, "")) != value:
            raise MediaError(
                f"scenario metadata mismatch in {path}: {key}={metadata.get(key)!r}, "
                f"expected={value!r}"
            )
    if int(metadata.get("seed", -1)) != int(row["seed"]):
        raise MediaError(f"scenario seed mismatch in {path}")
    for key in ("scenario_id", "split"):
        if FORBIDDEN_PUBLICATION_TOKENS.search(str(metadata.get(key, ""))):
            raise MediaError(f"scenario contains forbidden validation/historical metadata: {path}")

    robots = payload.get("robots")
    if not isinstance(robots, list) or len(robots) != 1 or not isinstance(robots[0], dict):
        raise MediaError(f"scenario must contain exactly one robot: {path}")
    robot_start = _finite_xy(robots[0].get("start"))
    robot_goal = _finite_xy(robots[0].get("goal"))
    if robot_start is None or robot_goal is None:
        raise MediaError(f"scenario robot start/goal is malformed: {path}")

    obstacles = payload.get("obstacles")
    if not isinstance(obstacles, dict):
        raise MediaError(f"scenario lacks obstacle configuration: {path}")
    raw_static = obstacles.get("static", [])
    if not isinstance(raw_static, list):
        raise MediaError(f"scenario static geometry is malformed: {path}")
    static_boxes = tuple(
        _shelf_box(obstacle, path) for obstacle in raw_static if isinstance(obstacle, Mapping)
    )
    if len(static_boxes) != len(raw_static):
        raise MediaError(f"scenario static geometry contains a non-object entry: {path}")
    raw_actors = obstacles.get("dynamic", [])
    if not isinstance(raw_actors, list):
        raise MediaError(f"scenario actor configuration is malformed: {path}")
    actor_routes: list[tuple[tuple[float, float], ...]] = []
    for actor in raw_actors:
        if not isinstance(actor, dict):
            raise MediaError(f"scenario actor configuration contains a non-object: {path}")
        route = _polyline(actor.get("waypoints"), maximum_points=1_000)
        if len(route) < 2:
            raise MediaError(f"scenario actor route contains fewer than two waypoints: {path}")
        actor_routes.append(route)
    return ScenarioEvidence(
        path=path,
        scenario_id=str(row["scenario_id"]),
        family=str(row["family"]),
        density=str(row["density"]),
        seed=int(row["seed"]),
        robot_start=robot_start,
        robot_goal=robot_goal,
        static_boxes=static_boxes,
        actor_routes=tuple(actor_routes),
    )


def _recovery_trigger_indices(episode: EpisodeTelemetry) -> tuple[int, ...]:
    active = np.asarray(
        [frame.recovery_state in {1, 2, 3, 4} for frame in episode.frames], dtype=bool
    )
    previous = np.concatenate((np.asarray([False]), active[:-1]))
    return tuple(int(index) for index in np.flatnonzero(active & ~previous))


def select_matched_test_evidence(
    results: pd.DataFrame,
    raw_dir: Path,
    scenario_root: Path = ROOT,
) -> MatchedEpisodeEvidence:
    """Select one SHA-verified, same-pair Base--PGRR test comparison.

    Eligibility first requires a PGRR trigger and configured static geometry
    plus actor routes.  The fixed ordering then prefers Base failure/PGRR goal,
    any outcome contrast, a PGRR goal, high density, more PGRR triggers, family,
    seed, and pair ID.  This is descriptive evidence selection, not metric
    filtering; the figure states ``n=1`` and the rule verbatim.
    """

    candidates: list[
        tuple[tuple[Any, ...], Mapping[str, Any], Mapping[str, Any], ScenarioEvidence]
    ] = []
    family_rank = {family: index for index, family in enumerate(PUBLICATION_FAMILIES)}
    density_rank = {"high": 0, "medium": 1, "low": 2}
    for pair_id, group in results.groupby("pair_id", sort=False, dropna=False):
        indexed = {str(row["source_policy"]): row.to_dict() for _, row in group.iterrows()}
        base_row = indexed["base"]
        pgrr_row = indexed["pgrr"]
        if not bool(base_row["included_in_algorithm_metrics"]) or not bool(
            pgrr_row["included_in_algorithm_metrics"]
        ):
            continue
        if float(pgrr_row["recovery_trigger_count"]) <= 0.0:
            continue
        scenario = load_scenario_evidence(pgrr_row, scenario_root)
        if not scenario.static_boxes or not scenario.actor_routes:
            continue
        base_outcome = str(base_row["outcome"])
        pgrr_outcome = str(pgrr_row["outcome"])
        if base_outcome != "GOAL_REACHED" and pgrr_outcome == "GOAL_REACHED":
            contrast = 0
        elif base_outcome != pgrr_outcome:
            contrast = 1
        elif pgrr_outcome == "GOAL_REACHED":
            contrast = 2
        else:
            contrast = 3
        rank = (
            contrast,
            density_rank[str(pgrr_row["density"])],
            -float(pgrr_row["recovery_trigger_count"]),
            family_rank[str(pgrr_row["family"])],
            int(pgrr_row["seed"]),
            str(pair_id),
        )
        candidates.append((rank, base_row, pgrr_row, scenario))
    if not candidates:
        raise MediaError(
            "complete test results contain no eligible PGRR-triggered pair with both "
            "configured static geometry and actor routes"
        )
    _, base_row, pgrr_row, scenario = min(candidates, key=lambda item: item[0])
    base = _verify_selected_episode(base_row, raw_dir)
    pgrr = _verify_selected_episode(pgrr_row, raw_dir)
    finite_timeline = all(
        frame.failure_score is not None and frame.distance_to_goal is not None
        for frame in pgrr.frames
    )
    if not finite_timeline:
        raise MediaError(
            f"selected PGRR raw JSONL lacks a complete measured timeline: {pgrr.jsonl_path}"
        )
    triggers = _recovery_trigger_indices(pgrr)
    declared_triggers = float(pgrr_row["recovery_trigger_count"])
    if not declared_triggers.is_integer() or int(declared_triggers) != len(triggers):
        raise MediaError(
            "selected PGRR raw trigger transitions disagree with results: "
            f"raw={len(triggers)}, declared={declared_triggers}"
        )
    return MatchedEpisodeEvidence(
        pair_id=str(pgrr_row["pair_id"]),
        base_row=base_row,
        pgrr_row=pgrr_row,
        base=base,
        pgrr=pgrr,
        scenario=scenario,
        selection_rule=(
            "eligible: PGRR trigger + configured static geometry + actor routes; order: "
            "Base failure/PGRR goal, outcome contrast, PGRR goal, density, trigger count, "
            "family, seed, pair_id"
        ),
    )


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


def _odometry_trajectory(episode: EpisodeTelemetry) -> np.ndarray[Any, np.dtype[np.float64]]:
    poses = [frame.odometry_pose for frame in episode.frames]
    if any(pose is None for pose in poses):
        raise MediaError(
            f"episode lacks a complete logged odometry trajectory: {episode.jsonl_path}"
        )
    return np.asarray(poses, dtype=np.float64)


def _box_vertices(
    box: tuple[float, float, float, float, float],
) -> np.ndarray[Any, np.dtype[np.float64]]:
    center_x, center_y, half_x, half_y, yaw = box
    local = np.asarray(
        [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)],
        dtype=np.float64,
    )
    rotation = np.asarray(
        [[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]],
        dtype=np.float64,
    )
    return local @ rotation.T + np.asarray([center_x, center_y], dtype=np.float64)


def _matched_bounds(evidence: MatchedEpisodeEvidence) -> tuple[float, float, float, float]:
    coordinates: list[tuple[float, float]] = [
        evidence.scenario.robot_start,
        evidence.scenario.robot_goal,
    ]
    for box in evidence.scenario.static_boxes:
        vertices = _box_vertices(box)
        for index in range(vertices.shape[0]):
            coordinates.append((float(vertices[index, 0]), float(vertices[index, 1])))
    for route in evidence.scenario.actor_routes:
        coordinates.extend(route)
    for episode in (evidence.base, evidence.pgrr):
        trajectory = _odometry_trajectory(episode)
        for index in range(trajectory.shape[0]):
            coordinates.append((float(trajectory[index, 0]), float(trajectory[index, 1])))
        for frame in episode.frames:
            coordinates.extend(frame.human_positions)
    values = np.asarray(coordinates, dtype=np.float64)
    minimum = np.min(values, axis=0)
    maximum = np.max(values, axis=0)
    span = np.maximum(maximum - minimum, np.asarray([2.0, 2.0]))
    margin = 0.06 * float(np.max(span)) + 0.35
    return (
        float(minimum[0] - margin),
        float(maximum[0] + margin),
        float(minimum[1] - margin),
        float(maximum[1] + margin),
    )


def _human_traces(episode: EpisodeTelemetry) -> tuple[np.ndarray[Any, np.dtype[np.float64]], ...]:
    actor_count = max((len(frame.human_positions) for frame in episode.frames), default=0)
    traces: list[np.ndarray[Any, np.dtype[np.float64]]] = []
    for actor_index in range(actor_count):
        positions = [
            frame.human_positions[actor_index]
            for frame in episode.frames
            if actor_index < len(frame.human_positions)
        ]
        if positions:
            traces.append(np.asarray(positions, dtype=np.float64))
    return tuple(traces)


def _draw_configured_environment(axis: Axes, scenario: ScenarioEvidence) -> None:
    for index, box in enumerate(scenario.static_boxes):
        axis.add_patch(
            Polygon(
                _box_vertices(box),
                closed=True,
                facecolor=LIGHT_GREY,
                edgecolor=MID_GREY,
                linewidth=0.55,
                hatch="////",
                label="configured shelf footprint" if index == 0 else None,
                zorder=0,
            )
        )
    for index, route in enumerate(scenario.actor_routes):
        values = np.asarray(route, dtype=np.float64)
        axis.plot(
            values[:, 0],
            values[:, 1],
            color=ORANGE,
            linestyle="--",
            linewidth=0.75,
            alpha=0.68,
            label="configured actor route" if index == 0 else None,
            zorder=1,
        )
        axis.scatter(
            [values[0, 0]],
            [values[0, 1]],
            marker="o",
            facecolor="white",
            edgecolor=ORANGE,
            linewidth=0.55,
            s=12,
            zorder=2,
        )
        axis.scatter(
            [values[-1, 0]],
            [values[-1, 1]],
            marker=">",
            color=ORANGE,
            linewidth=0.0,
            s=14,
            zorder=2,
        )


def _draw_matched_episode(
    axis: Axes,
    episode: EpisodeTelemetry,
    scenario: ScenarioEvidence,
    bounds: tuple[float, float, float, float],
    *,
    method_label: str,
    trajectory_color: str,
    panel_label: str,
) -> None:
    _draw_configured_environment(axis, scenario)
    for index, trace in enumerate(_human_traces(episode)):
        axis.plot(
            trace[:, 0],
            trace[:, 1],
            color=ORANGE,
            linewidth=0.65,
            alpha=0.42,
            label="logged actor trace" if index == 0 else None,
            zorder=2,
        )
    trajectory = _odometry_trajectory(episode)
    axis.plot(
        trajectory[:, 0],
        trajectory[:, 1],
        color=trajectory_color,
        linewidth=1.65,
        label="logged odometry trajectory",
        zorder=4,
    )
    axis.scatter(
        [scenario.robot_start[0]],
        [scenario.robot_start[1]],
        marker="o",
        facecolor="white",
        edgecolor=INK,
        linewidth=0.8,
        s=32,
        label="configured start",
        zorder=6,
    )
    axis.scatter(
        [scenario.robot_goal[0]],
        [scenario.robot_goal[1]],
        marker="*",
        color=TEAL,
        edgecolor="white",
        linewidth=0.45,
        s=68,
        label="configured goal",
        zorder=6,
    )
    axis.scatter(
        [trajectory[-1, 0]],
        [trajectory[-1, 1]],
        marker="X",
        color=trajectory_color,
        edgecolor="white",
        linewidth=0.55,
        s=46,
        label="terminal odometry pose",
        zorder=7,
    )
    outcome = episode.outcome.upper().replace("_", " ")
    axis.set_title(f"({panel_label}) {method_label} — {outcome}", loc="left", fontweight="bold")
    axis.set_xlim(bounds[0], bounds[1])
    axis.set_ylim(bounds[2], bounds[3])
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("world x [m]")
    axis.grid(color=LIGHT_GREY, linewidth=0.48)
    axis.set_axisbelow(True)


def _save_publication_pdf(figure: Figure, output: Path) -> None:
    destination = _root_path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        figure.savefig(
            destination,
            metadata={"Creator": "PGRR telemetry renderer"},
        )
    except OSError as error:
        raise MediaError(f"cannot write publication figure {destination}: {error}") from error
    finally:
        plt.close(figure)


def matched_trajectory_figure(evidence: MatchedEpisodeEvidence, output: Path) -> None:
    """Render one honest same-condition Base--PGRR odometry comparison."""

    bounds = _matched_bounds(evidence)
    figure, axes = plt.subplots(
        1,
        2,
        figsize=(7.16, 4.05),
        sharex=True,
        sharey=True,
        constrained_layout=False,
    )
    figure.subplots_adjust(left=0.075, right=0.99, bottom=0.31, top=0.77, wspace=0.18)
    _draw_matched_episode(
        axes[0],
        evidence.base,
        evidence.scenario,
        bounds,
        method_label="Base (DWB)",
        trajectory_color=BLUE,
        panel_label="a",
    )
    _draw_matched_episode(
        axes[1],
        evidence.pgrr,
        evidence.scenario,
        bounds,
        method_label="PGRR",
        trajectory_color=TEAL,
        panel_label="b",
    )
    axes[0].set_ylabel("world y [m]")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.145),
        frameon=False,
        fontsize=6.6,
        handlelength=1.8,
    )
    scenario = evidence.scenario
    figure.suptitle(
        "Matched test condition: recorded Base and PGRR navigation",
        fontsize=9.5,
        fontweight="bold",
        y=0.985,
    )
    figure.text(
        0.5,
        0.925,
        f"pair_id={evidence.pair_id}",
        ha="center",
        fontsize=6.5,
        color=INK,
    )
    figure.text(
        0.5,
        0.885,
        f"{scenario.family} / {scenario.density} | seed={scenario.seed} | "
        "n=1 matched pair (descriptive, not an aggregate)",
        ha="center",
        fontsize=7.1,
        color=INK,
    )
    figure.text(
        0.5,
        0.018,
        f"{TELEMETRY_NOTICE}. Robot curves: logged odometry; actor traces: logged simulator "
        "positions.\nDashed actor routes and shelf footprints: SHA-verified scenario JSON; "
        "separate from any Gazebo camera capture.\n"
        f"SHA-256 verified raw: Base={str(evidence.base_row['raw_sha256'])[:12]}…, "
        f"PGRR={str(evidence.pgrr_row['raw_sha256'])[:12]}…. Selection eligibility: PGRR "
        "trigger + geometry/routes.\nFixed rank: outcome contrast, density, triggers, family, "
        "seed, pair_id.",
        ha="center",
        va="bottom",
        fontsize=5.45,
        color=MID_GREY,
        linespacing=1.18,
    )
    _save_publication_pdf(figure, output)


def pgrr_recovery_timeline_figure(evidence: MatchedEpisodeEvidence, output: Path) -> None:
    """Render measured goal distance, score, state, action, and trigger events."""

    episode = evidence.pgrr
    time = np.asarray([frame.timestamp for frame in episode.frames], dtype=np.float64)
    distance = np.asarray([frame.distance_to_goal for frame in episode.frames], dtype=np.float64)
    score = np.asarray([frame.failure_score for frame in episode.frames], dtype=np.float64)
    states = np.asarray([frame.recovery_state for frame in episode.frames], dtype=np.int64)
    actions = np.asarray([frame.recovery_action for frame in episode.frames], dtype=np.int64)
    if not bool(np.isfinite(distance).all()) or bool((distance < 0.0).any()):
        raise MediaError("selected PGRR telemetry has an invalid distance-to-goal trace")
    if not bool(np.isfinite(score).all()) or bool(((score < 0.0) | (score > 1.0)).any()):
        raise MediaError("selected PGRR telemetry has an invalid failure-score trace")
    trigger_indices = _recovery_trigger_indices(episode)
    active = np.isin(states, [1, 2, 3, 4])
    starts = np.flatnonzero(active & np.concatenate((np.asarray([True]), ~active[:-1])))
    ends = np.flatnonzero(active & np.concatenate((~active[1:], np.asarray([True]))))

    figure, axes = plt.subplots(
        4,
        1,
        figsize=(7.16, 5.05),
        sharex=True,
        constrained_layout=False,
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.0, 1.12)},
    )
    figure.subplots_adjust(left=0.165, right=0.975, bottom=0.16, top=0.82, hspace=0.20)
    mark_every = max(1, len(time) // 24)
    axes[0].plot(
        time,
        distance,
        color=BLUE,
        marker="s",
        markerfacecolor="white",
        markeredgewidth=0.65,
        markevery=mark_every,
        linewidth=1.2,
    )
    axes[0].set_ylabel("Goal distance [m]")
    axes[1].plot(
        time,
        score,
        color=ORANGE,
        marker="o",
        markerfacecolor="white",
        markeredgewidth=0.65,
        markevery=mark_every,
        linewidth=1.2,
    )
    axes[1].set_ylabel("Failure score")
    axes[1].set_ylim(-0.04, 1.04)
    axes[2].step(time, states, where="post", color=TEAL, linewidth=1.3)
    present_states = sorted(set(int(value) for value in states))
    axes[2].set_yticks(
        present_states,
        [
            {
                0: "NORMAL",
                1: "PENDING",
                2: "RECOVERY",
                3: "REJOIN",
                4: "E-STOP",
                5: "FAILED",
                6: "SUCCEEDED",
            }[value]
            for value in present_states
        ],
    )
    axes[2].set_ylabel("Recovery state")
    axes[3].step(time, actions, where="post", color=BLUE, linewidth=1.15)
    present_actions = sorted(set(int(value) for value in actions))

    def short_action(value: int) -> str:
        if 0 <= value < 21:
            radius = RADII_METERS[value // len(ANGLES_DEGREES)]
            angle = ANGLES_DEGREES[value % len(ANGLES_DEGREES)]
            return f"{value}: SG {radius:.1f}/{angle:+d}°"
        return f"{value}: {action_label(value)}"

    axes[3].set_yticks(
        present_actions,
        [short_action(value) for value in present_actions],
    )
    axes[3].set_ylabel("Action")
    axes[3].set_xlabel("simulation time [s]")

    for start, end in zip(starts, ends, strict=True):
        start_time = float(time[start])
        end_time = float(time[min(end + 1, len(time) - 1)])
        for axis in axes:
            axis.axvspan(start_time, end_time, color=TEAL, alpha=0.07, zorder=0)
    for trigger_number, index in enumerate(trigger_indices, start=1):
        trigger_time = float(time[index])
        for axis in axes:
            axis.axvline(trigger_time, color=INK, linestyle="--", linewidth=0.75, alpha=0.7)
        reason = episode.frames[index].recovery_reason
        annotation = f"trigger {trigger_number}"
        if reason:
            annotation += f": {reason}"
        axes[0].annotate(
            annotation,
            xy=(trigger_time, float(distance[index])),
            xytext=(4, 7),
            textcoords="offset points",
            fontsize=6.3,
            color=INK,
            arrowprops={"arrowstyle": "-", "color": INK, "linewidth": 0.55},
        )
    for axis in axes:
        axis.grid(axis="y", color=LIGHT_GREY, linewidth=0.5)
        axis.set_axisbelow(True)

    scenario = evidence.scenario
    terminal = episode.outcome.upper().replace("_", " ")
    figure.suptitle(
        "Recorded PGRR recovery timeline",
        fontsize=9.5,
        fontweight="bold",
        y=0.985,
    )
    figure.text(
        0.5,
        0.925,
        f"pair_id={evidence.pair_id}",
        ha="center",
        fontsize=6.5,
        color=INK,
    )
    figure.text(
        0.5,
        0.885,
        f"{scenario.family} / {scenario.density} | seed={scenario.seed} | "
        f"triggers={len(trigger_indices)} | terminal={terminal} | n=1",
        ha="center",
        fontsize=7.2,
        color=INK,
    )
    figure.text(
        0.5,
        0.018,
        f"{TELEMETRY_NOTICE}. Every trace and trigger is reconstructed from the "
        f"SHA-256-verified test JSONL ({str(evidence.pgrr_row['raw_sha256'])[:12]}…).\n"
        "No values come from validation summaries; this is separate from a Gazebo camera frame.",
        ha="center",
        va="bottom",
        fontsize=6.0,
        color=MID_GREY,
    )
    _save_publication_pdf(figure, output)


def render_matched_final_figures(
    results_path: Path,
    raw_dir: Path,
    figure_dir: Path,
    scenario_root: Path = ROOT,
) -> tuple[MatchedEpisodeEvidence, MatchedMediaArtifacts]:
    """Validate final test evidence and generate the two fixed publication PDFs."""

    results = load_complete_moderate_test_results(results_path)
    evidence = select_matched_test_evidence(results, raw_dir, scenario_root)
    destination = _root_path(figure_dir)
    artifacts = MatchedMediaArtifacts(
        trajectory_pdf=destination / MATCHED_TRAJECTORY_NAME,
        timeline_pdf=destination / PGRR_TIMELINE_NAME,
    )
    matched_trajectory_figure(evidence, artifacts.trajectory_pdf)
    pgrr_recovery_timeline_figure(evidence, artifacts.timeline_pdf)
    return evidence, artifacts


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
        writer_context: Any = imageio.get_writer(
            destination,
            format="FFMPEG",  # type: ignore[arg-type]
            mode="I",
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=2,
            ffmpeg_log_level="error",
            output_params=["-metadata", "comment=Telemetry reconstruction; not a camera image"],
        )
        with writer_context as writer:
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
                canvas: Any = figure.canvas
                rgba = np.asarray(canvas.buffer_rgba())
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
    parser.add_argument(
        "--matched-final",
        action="store_true",
        help=(
            "generate the SHA-verified, same-pair Base/PGRR trajectory and PGRR timeline "
            "from the complete moderate test"
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--results",
        type=Path,
        help=(
            "results Parquet; defaults to outputs/moderate/final/results.parquet with "
            "--matched-final and outputs/final/results.parquet otherwise"
        ),
    )
    source.add_argument("--jsonl", type=Path, help="render this exact recorded JSONL stream")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--scenario-root",
        type=Path,
        default=ROOT,
        help="root used to resolve SHA-bound scenario_path values (default: repository root)",
    )
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
    if args.matched_final and args.jsonl is not None:
        parser.error("--matched-final requires the complete --results table, not --jsonl")
    if args.matched_final and args.episode_id is not None:
        parser.error("--episode-id cannot override deterministic matched-final selection")

    try:
        if args.matched_final:
            results = args.results or Path("outputs/moderate/final/results.parquet")
            evidence, matched = render_matched_final_figures(
                results,
                args.raw_dir,
                args.figure_dir,
                args.scenario_root,
            )
            print(f"pair_id: {evidence.pair_id}")
            print(f"selection: {evidence.selection_rule}")
            print(f"Base source: {evidence.base.jsonl_path}")
            print(f"PGRR source: {evidence.pgrr.jsonl_path}")
            print(f"trajectory PDF: {matched.trajectory_pdf}")
            print(f"timeline PDF: {matched.timeline_pdf}")
            return 0
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
