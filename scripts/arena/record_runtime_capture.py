#!/usr/bin/env python3
"""Validate and record privacy-safe provenance for a real runtime screenshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"artifact must be inside the repository: {path}") from error


def _validate_clean_png(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG":
            raise ValueError(f"runtime capture is not PNG: {path}")
        if image.width < 640 or image.height < 480:
            raise ValueError("runtime capture is below 640x480")
        if image.info:
            raise ValueError(
                "runtime PNG contains ancillary metadata and must be sanitized: "
                + ", ".join(sorted(image.info))
            )
        return {"width_px": image.width, "height_px": image.height}


def record_capture(
    *,
    root: Path,
    screenshot: Path,
    paper_copy: Path,
    metadata_output: Path,
    window_info: Path,
    scenario: Path,
    outcome: Path,
    runtime_log: Path,
    capture_log: Path,
    git_commit: str,
    arena_image_id: str,
    ros_domain_id: int,
    gazebo_partition: str,
    episode_id: str,
    captured_at: str,
) -> dict[str, Any]:
    dimensions = _validate_clean_png(screenshot)
    scenario_payload = json.loads(scenario.read_text(encoding="utf-8"))
    scenario_metadata = scenario_payload.get("ramp_metadata", {})
    outcome_payload = json.loads(outcome.read_text(encoding="utf-8"))
    window_payload = json.loads(window_info.read_text(encoding="utf-8"))
    selected_window = window_payload.get("selected_window", {})
    selected_title = str(selected_window.get("title", ""))
    if re.search(r"Gazebo|gz sim", selected_title, flags=re.IGNORECASE) is None:
        raise ValueError(f"selected X11 window is not identifiable as Gazebo: {selected_title!r}")
    visual_validation = window_payload.get("visual_validation", {})
    scene_stddev = float(visual_validation.get("scene_viewport_grayscale_stddev", 0.0))
    scene_colors = int(visual_validation.get("scene_viewport_unique_colors", 0))
    if scene_stddev < 15.0 or scene_colors < 300:
        raise ValueError("Gazebo Scene3D viewport evidence is blank or incomplete")
    camera_framing = window_payload.get("capture_context", {})
    if (
        camera_framing.get("framing") != "scenario_midpoint_oblique"
        or camera_framing.get("transport_service") != "/gui/move_to/pose"
    ):
        raise ValueError("runtime screenshot is missing the reproducible Gazebo camera pose")
    if outcome_payload.get("episode_id") != episode_id:
        raise ValueError("episode outcome does not match the requested capture episode")
    valid_outcomes = {"GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE"}
    if outcome_payload.get("outcome") not in valid_outcomes:
        raise ValueError("runtime screenshot episode has an infrastructure-only outcome")
    if not runtime_log.is_file() or not capture_log.is_file():
        raise FileNotFoundError("capture logs are incomplete")
    paper_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(screenshot, paper_copy)
    if _sha256(screenshot) != _sha256(paper_copy):
        raise RuntimeError("paper screenshot copy differs from the captured PNG")
    payload: dict[str, Any] = {
        "artifact_type": "real_arena_gazebo_gui_screenshot",
        "capture_backend": window_payload.get("capture_backend"),
        "capture_target": "Gazebo GUI window",
        "captured_at_utc": captured_at,
        "dimensions": dimensions,
        "episode_id": episode_id,
        "episode_outcome": outcome_payload.get("outcome"),
        "git_commit": git_commit,
        "arena_commit": "c2ff4a87e8686013b53f1e9cd8b01b3ab04fbce4",
        "arena_image_id": arena_image_id,
        "launch_profile": {
            "simulator": "gazebo",
            "headless": 0,
            "robot": "jackal",
            "local_planner": "dwb",
            "software_rendering": True,
        },
        "isolation": {
            "ros_domain_id": ros_domain_id,
            "gazebo_partition": gazebo_partition,
        },
        "scenario": {
            "path": _relative(root, scenario),
            "scenario_id": scenario_metadata.get("scenario_id"),
            "family": scenario_metadata.get("family"),
            "density": scenario_metadata.get("density"),
            "seed": scenario_metadata.get("seed"),
            "split": scenario_metadata.get("split"),
        },
        "artifacts": {
            "screenshot": _relative(root, screenshot),
            "paper_copy": _relative(root, paper_copy),
            "screenshot_sha256": _sha256(screenshot),
            "outcome": _relative(root, outcome),
            "runtime_log": _relative(root, runtime_log),
            "capture_log": _relative(root, capture_log),
            "window_info": _relative(root, window_info),
        },
        "window": selected_window,
        "camera_framing": camera_framing,
        "visual_validation": visual_validation,
        "reproduce_command": (
            f"SCENARIO={_relative(root, scenario)} scripts/arena/capture_gazebo_snapshot.sh"
        ),
        "provenance_note": (
            "Pixels were copied from the mapped Gazebo X11 window while the "
            "same Arena/Nav2 episode produced the referenced raw log and outcome."
        ),
    }
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--paper-copy", required=True, type=Path)
    parser.add_argument("--metadata-output", required=True, type=Path)
    parser.add_argument("--window-info", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--runtime-log", required=True, type=Path)
    parser.add_argument("--capture-log", required=True, type=Path)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--arena-image-id", required=True)
    parser.add_argument("--ros-domain-id", required=True, type=int)
    parser.add_argument("--gazebo-partition", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--captured-at", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record_capture(
        root=args.root,
        screenshot=args.screenshot,
        paper_copy=args.paper_copy,
        metadata_output=args.metadata_output,
        window_info=args.window_info,
        scenario=args.scenario,
        outcome=args.outcome,
        runtime_log=args.runtime_log,
        capture_log=args.capture_log,
        git_commit=args.git_commit,
        arena_image_id=args.arena_image_id,
        ros_domain_id=args.ros_domain_id,
        gazebo_partition=args.gazebo_partition,
        episode_id=args.episode_id,
        captured_at=args.captured_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
