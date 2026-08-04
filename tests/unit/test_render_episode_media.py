from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/paper/render_episode_media.py"
    spec = importlib.util.spec_from_file_location("render_episode_media", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


media = _module()


def _records() -> list[dict[str, object]]:
    return [
        {
            "timestamp": 0.0,
            "robot_pose": [0.0, 0.0, 0.0],
            "goal": [3.0, 0.0, 0.0],
            "global_path": [[0.0, 0.0], [1.5, 0.0], [3.0, 0.0]],
            "failure_score": 0.1,
            "distance_to_goal": 3.0,
            "recovery_state": 0,
            "recovery_action": 24,
            "collision": False,
            "timeout": False,
            "privileged": {
                "robot_pose": [0.0, 0.0, 0.0],
                "human_positions": [[1.3, 0.4], [2.0, -0.5]],
            },
        },
        {
            "timestamp": 1.0,
            "robot_pose": [0.5, 0.0, 0.1],
            "goal": [3.0, 0.0, 0.0],
            "global_path": [[0.5, 0.0], [1.5, 0.1], [3.0, 0.0]],
            "failure_score": 0.82,
            "distance_to_goal": 2.5,
            "recovery_state": 2,
            "recovery_action": 3,
            "collision": False,
            "timeout": False,
            "privileged": {
                "robot_pose": [0.48, 0.01, 0.1],
                "human_positions": [[1.1, 0.2], [1.8, -0.3]],
            },
        },
        {
            "timestamp": 2.0,
            "robot_pose": [1.4, 0.1, 0.0],
            "goal": [3.0, 0.0, 0.0],
            "global_path": [[1.4, 0.1], [3.0, 0.0]],
            "failure_score": 0.32,
            "distance_to_goal": 1.6,
            "recovery_state": 3,
            "recovery_action": 24,
            "collision": False,
            "timeout": False,
            "privileged": {
                "robot_pose": [1.39, 0.1, 0.0],
                "human_positions": [[0.9, 0.0], [1.4, -0.1]],
            },
        },
        {
            "timestamp": 3.0,
            "robot_pose": [3.0, 0.0, 0.0],
            "goal": [3.0, 0.0, 0.0],
            "global_path": [[3.0, 0.0]],
            "failure_score": 0.02,
            "distance_to_goal": 0.0,
            "recovery_state": 6,
            "recovery_action": 24,
            "collision": False,
            "timeout": False,
            "privileged": {
                "robot_pose": [3.0, 0.0, 0.0],
                "human_positions": [[0.5, -0.2], [1.0, 0.15]],
            },
        },
    ]


def _write_episode(directory: Path, episode_id: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stream = directory / f"{episode_id}.jsonl"
    stream.write_text("".join(json.dumps(row) + "\n" for row in _records()), encoding="utf-8")
    stream.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "scenario_id": "crossing_flow_high_test_s1",
                "source_policy": "bc",
            }
        ),
        encoding="utf-8",
    )
    stream.with_suffix(".outcome.json").write_text(
        json.dumps({"episode_id": episode_id, "outcome": "GOAL_REACHED"}),
        encoding="utf-8",
    )
    return stream


def test_load_and_render_keyframes_from_synthetic_jsonl(tmp_path: Path) -> None:
    stream = _write_episode(tmp_path / "raw", "synthetic_success")

    episode = media.load_telemetry(stream)
    artifacts = media.render_media(
        episode,
        figure_dir=tmp_path / "figures",
        video_dir=tmp_path / "videos",
        make_video=False,
    )

    assert episode.frames[1].robot_pose == (0.48, 0.01, 0.1)
    assert episode.frames[1].robot_pose_source == "privileged simulator pose"
    assert media.keyframe_indices(episode.frames) == (0, 1, 2, 3)
    assert artifacts.keyframes_pdf.is_file()
    assert artifacts.keyframes_pdf.stat().st_size > 1_000
    assert artifacts.keyframes_png.is_file()
    assert artifacts.keyframes_png.stat().st_size > 1_000
    assert artifacts.video_mp4 is None


def test_results_selection_is_deterministic_and_prefers_triggered_success(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    for episode_id in ("plain_success", "medium_triggered", "high_triggered"):
        _write_episode(raw, episode_id)
    results = pd.DataFrame(
        [
            {
                "episode_id": "plain_success",
                "source_policy": "bc",
                "included_in_algorithm_metrics": True,
                "outcome": "GOAL_REACHED",
                "recovery_trigger_count": 0,
                "density": "high",
                "family": "doorway_bottleneck",
                "seed": 3,
            },
            {
                "episode_id": "medium_triggered",
                "source_policy": "bc",
                "included_in_algorithm_metrics": True,
                "outcome": "GOAL_REACHED",
                "recovery_trigger_count": 2,
                "density": "medium",
                "family": "crossing_flow",
                "seed": 2,
            },
            {
                "episode_id": "high_triggered",
                "source_policy": "bc",
                "included_in_algorithm_metrics": True,
                "outcome": "GOAL_REACHED",
                "recovery_trigger_count": 1,
                "density": "high",
                "family": "head_on_corridor",
                "seed": 1,
            },
            {
                "episode_id": "excluded",
                "source_policy": "bc",
                "included_in_algorithm_metrics": False,
                "outcome": "GOAL_REACHED",
                "recovery_trigger_count": 99,
                "density": "high",
                "family": "blind_corner",
                "seed": 0,
            },
        ]
    )
    results_path = tmp_path / "results.parquet"
    results.to_parquet(results_path, index=False)

    selected = media.select_representative(results_path, raw, method="bc")

    assert selected == raw / "high_triggered.jsonl"


def test_missing_final_results_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = media.main(
        [
            "--results",
            str(tmp_path / "missing.parquet"),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--skip-video",
        ]
    )

    assert status == 2
    assert "final results are unavailable" in capsys.readouterr().err


def test_non_monotonic_synthetic_jsonl_is_rejected(tmp_path: Path) -> None:
    stream = _write_episode(tmp_path, "bad_time")
    rows = _records()
    rows[2]["timestamp"] = 0.5
    stream.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(media.MediaError, match="not monotonic"):
        media.load_telemetry(stream)
