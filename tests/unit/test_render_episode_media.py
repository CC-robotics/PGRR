from __future__ import annotations

import hashlib
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


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bound_episode(
    raw_dir: Path,
    *,
    episode_id: str,
    scenario_id: str,
    source_policy: str,
    seed: int,
    commit: str,
    outcome: str,
    records: list[dict[str, object]],
) -> tuple[Path, str, str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stream = raw_dir / f"{episode_id}.jsonl"
    stream.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    metadata = stream.with_suffix(".metadata.json")
    metadata.write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "scenario_id": scenario_id,
                "map_id": "map_empty",
                "seed": seed,
                "split": "test",
                "planner_id": "dwb",
                "source_policy": source_policy,
                "project_commit": commit,
            }
        ),
        encoding="utf-8",
    )
    outcome_path = stream.with_suffix(".outcome.json")
    outcome_path.write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "outcome": outcome,
                "sample_count": len(records),
            }
        ),
        encoding="utf-8",
    )
    return stream, _digest(stream), _digest(metadata), _digest(outcome_path)


def _complete_matched_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    commit = "b" * 40
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir(parents=True)
    raw_dir = tmp_path / "raw"
    rows: list[dict[str, object]] = []
    selected_pair = ""
    selected_pgrr_episode = ""
    selected_scenario_path = scenario_dir / "selected_test_scenario.json"
    selected_scenario_sha = ""

    for family_index, family in enumerate(media.PUBLICATION_FAMILIES):
        for density_index, density in enumerate(media.PUBLICATION_DENSITIES):
            for replicate in range(media.PUBLICATION_REPLICATES_PER_CELL):
                seed = 90_000 + 100 * family_index + 10 * density_index + replicate
                scenario_id = f"{family}_{density}_test_moderate_v6_r{replicate:02d}_s{seed}"
                pair_id = f"{scenario_id}_seed{seed}"
                is_selected = family == "head_on_corridor" and density == "high" and replicate == 0
                if is_selected:
                    selected_pair = pair_id
                    selected_scenario_path.write_text(
                        json.dumps(
                            {
                                "obstacles": {
                                    "dynamic": [
                                        {
                                            "name": "ped_00",
                                            "model": "gazebo_actor",
                                            "pos": [2.7, -0.5, 1.57],
                                            "waypoints": [
                                                [2.7, -0.5, 1.57],
                                                [2.7, 0.8, 1.57],
                                            ],
                                        }
                                    ],
                                    "interactive": [],
                                    "static": [
                                        {
                                            "model": "shelf",
                                            "name": "wall_00",
                                            "pos": [1.2, -0.8, 0.0],
                                        },
                                        {
                                            "model": "shelf",
                                            "name": "wall_01",
                                            "pos": [1.2, 0.8, 0.0],
                                        },
                                    ],
                                },
                                "ramp_metadata": {
                                    "scenario_id": scenario_id,
                                    "family": family,
                                    "density": density,
                                    "seed": seed,
                                    "split": "test",
                                    "replicate": replicate,
                                    "map_id": "map_empty",
                                },
                                "robots": [{"start": [0.0, 0.0, 0.0], "goal": [3.0, 0.0, 0.0]}],
                            }
                        ),
                        encoding="utf-8",
                    )
                    selected_scenario_sha = _digest(selected_scenario_path)

                for method in media.PUBLICATION_METHODS:
                    episode_id = f"{scenario_id}_eval_{method}_a0_dwb"
                    outcome = "GOAL_REACHED"
                    trigger_count = 0
                    raw_sha = "1" * 64
                    metadata_sha = "2" * 64
                    outcome_sha = "3" * 64
                    if is_selected and method == "base":
                        outcome = "COLLISION"
                        base_records = [dict(record) for record in _records()]
                        for index, record in enumerate(base_records):
                            record["recovery_state"] = 0 if index < len(base_records) - 1 else 5
                            record["recovery_action"] = 24
                            record["failure_score"] = min(0.95, 0.15 + 0.2 * index)
                            record["distance_to_goal"] = 3.0 - 0.35 * index
                            record["robot_pose"] = [0.35 * index, 0.03 * index, 0.0]
                            privileged = dict(record["privileged"])  # type: ignore[arg-type]
                            privileged["robot_pose"] = [0.35 * index, 0.03 * index, 0.0]
                            record["privileged"] = privileged
                            record["collision"] = index == len(base_records) - 1
                        _, raw_sha, metadata_sha, outcome_sha = _write_bound_episode(
                            raw_dir,
                            episode_id=episode_id,
                            scenario_id=scenario_id,
                            source_policy=method,
                            seed=seed,
                            commit=commit,
                            outcome=outcome,
                            records=base_records,
                        )
                    elif is_selected and method == "pgrr":
                        trigger_count = 1
                        pgrr_records = [dict(record) for record in _records()]
                        pgrr_records[1]["recovery_reason"] = "freeze_risk"
                        _, raw_sha, metadata_sha, outcome_sha = _write_bound_episode(
                            raw_dir,
                            episode_id=episode_id,
                            scenario_id=scenario_id,
                            source_policy=method,
                            seed=seed,
                            commit=commit,
                            outcome=outcome,
                            records=pgrr_records,
                        )
                        selected_pgrr_episode = episode_id
                    rows.append(
                        {
                            "episode_id": episode_id,
                            "pair_id": pair_id,
                            "scenario_id": scenario_id,
                            "family": family,
                            "density": density,
                            "seed": seed,
                            "replicate": replicate,
                            "split": "test",
                            "source_policy": method,
                            "outcome": outcome,
                            "included_in_algorithm_metrics": True,
                            "project_commit": commit,
                            "recovery_trigger_count": trigger_count,
                            "sample_count": 4 if is_selected and method in {"base", "pgrr"} else 1,
                            "raw_sha256": raw_sha,
                            "metadata_sha256": metadata_sha,
                            "outcome_sha256": outcome_sha,
                            "scenario_path": (
                                str(selected_scenario_path.relative_to(tmp_path))
                                if is_selected
                                else f"scenarios/generated/moderate_v6/{scenario_id}.json"
                            ),
                            "scenario_sha256": (selected_scenario_sha if is_selected else "4" * 64),
                        }
                    )
    results = tmp_path / "results.parquet"
    pd.DataFrame(rows).to_parquet(results, index=False)
    return results, raw_dir, tmp_path, selected_pair, selected_pgrr_episode


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


def test_complete_test_generates_sha_verified_matched_publication_figures(
    tmp_path: Path,
) -> None:
    results, raw_dir, scenario_root, selected_pair, _ = _complete_matched_fixture(tmp_path)

    evidence, artifacts = media.render_matched_final_figures(
        results,
        raw_dir,
        tmp_path / "figures",
        scenario_root,
    )

    assert evidence.pair_id == selected_pair
    assert evidence.base_row["pair_id"] == evidence.pgrr_row["pair_id"]
    assert evidence.base.outcome == "COLLISION"
    assert evidence.pgrr.outcome == "GOAL_REACHED"
    assert evidence.pgrr.frames[1].odometry_pose == (0.5, 0.0, 0.1)
    assert evidence.pgrr.frames[1].robot_pose == (0.48, 0.01, 0.1)
    assert len(evidence.scenario.static_boxes) == 2
    assert len(evidence.scenario.actor_routes) == 1
    assert artifacts.trajectory_pdf.name == media.MATCHED_TRAJECTORY_NAME
    assert artifacts.timeline_pdf.name == media.PGRR_TIMELINE_NAME
    assert artifacts.trajectory_pdf.stat().st_size > 2_000
    assert artifacts.timeline_pdf.stat().st_size > 2_000


def test_matched_publication_rejects_partial_or_validation_results(tmp_path: Path) -> None:
    results, _, _, _, _ = _complete_matched_fixture(tmp_path)
    frame = pd.read_parquet(results)
    frame.iloc[:-1].to_parquet(results, index=False)
    with pytest.raises(media.MediaError, match="require 600 rows"):
        media.load_complete_moderate_test_results(results)

    results, _, _, _, _ = _complete_matched_fixture(tmp_path / "validation_case")
    frame = pd.read_parquet(results)
    frame["split"] = "validation"
    frame.to_parquet(results, index=False)
    with pytest.raises(media.MediaError, match="locked test split"):
        media.load_complete_moderate_test_results(results)


def test_matched_publication_rejects_historical_identifiers(tmp_path: Path) -> None:
    results, _, _, _, _ = _complete_matched_fixture(tmp_path)
    frame = pd.read_parquet(results)
    pair_id = str(frame.iloc[0]["pair_id"])
    frame.loc[frame["pair_id"] == pair_id, "scenario_id"] = "historical_test_condition"
    frame.to_parquet(results, index=False)

    with pytest.raises(media.MediaError, match="validation/historical"):
        media.load_complete_moderate_test_results(results)


def test_matched_publication_rejects_tampered_raw_sha(tmp_path: Path) -> None:
    results, raw_dir, scenario_root, _, selected_pgrr_episode = _complete_matched_fixture(tmp_path)
    stream = raw_dir / f"{selected_pgrr_episode}.jsonl"
    stream.write_bytes(stream.read_bytes() + b"\n")
    complete = media.load_complete_moderate_test_results(results)

    with pytest.raises(media.MediaError, match="raw JSONL SHA-256 mismatch"):
        media.select_matched_test_evidence(complete, raw_dir, scenario_root)


def test_matched_publication_rejects_pair_metadata_mismatch(tmp_path: Path) -> None:
    results, _, _, _, _ = _complete_matched_fixture(tmp_path)
    frame = pd.read_parquet(results)
    frame.loc[0, "seed"] = int(frame.loc[0, "seed"]) + 1
    frame.to_parquet(results, index=False)

    with pytest.raises(media.MediaError, match="pair metadata mismatch"):
        media.load_complete_moderate_test_results(results)
