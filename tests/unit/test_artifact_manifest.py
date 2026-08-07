from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paper/build_artifact_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_artifact_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, content: bytes = b"artifact\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write(path, (json.dumps(payload, sort_keys=True) + "\n").encode())


def _write_pdf(path: Path, pages: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.new("RGB", (10, 10), color="white") for _ in range(pages)]
    images[0].save(path, save_all=True, append_images=images[1:])


def _write_presentation(
    path: Path,
    slides: int = 30,
    *,
    modified_by: str = "Charles Chen",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for number in range(1, slides + 1):
            archive.writestr(f"ppt/slides/slide{number}.xml", "<p:sld/>")
        archive.writestr(
            "docProps/core.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
 <dc:subject>stage=test; fixture</dc:subject>
 <dc:creator>Charles Chen</dc:creator>
 <cp:lastModifiedBy>{modified_by}</cp:lastModifiedBy>
</cp:coreProperties>""",
        )


_VIDEO_BYTES: bytes | None = None


def _write_video(path: Path) -> None:
    global _VIDEO_BYTES
    if _VIDEO_BYTES is None:
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "fixture.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=32x24:d=0.2:r=10",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(generated),
                ],
                check=True,
            )
            _VIDEO_BYTES = generated.read_bytes()
    _write(path, _VIDEO_BYTES)


def _complete_fixture(root: Path) -> None:
    for relative in (
        MODULE.DEFAULT_CONFIG,
        MODULE.DEFAULT_BASELINE_CONFIG,
        MODULE.DEFAULT_UNIFORM_CHECKPOINT,
        MODULE.DEFAULT_CHECKPOINT,
        MODULE.DEFAULT_SUMMARY,
        MODULE.DEFAULT_STATISTICS,
        MODULE.DEFAULT_FAILURE_ANALYSIS,
        MODULE.DEFAULT_OFFLINE_ABLATION_CSV,
        MODULE.DEFAULT_OFFLINE_ABLATION_JSON,
        MODULE.DEFAULT_MAIN_TEX,
        MODULE.DEFAULT_REFERENCES,
        MODULE.DEFAULT_CLAIM_MATRIX,
        MODULE.DEFAULT_ENVIRONMENT_LOCK,
        MODULE.DEFAULT_REQUIREMENTS_LOCK,
        MODULE.DEFAULT_ARENA_LOCK,
        MODULE.DEFAULT_DEPENDENCY_MANIFEST,
        MODULE.DEFAULT_TEST_SPLIT,
        MODULE.DEFAULT_FAILURE_CONFIG,
        MODULE.DEFAULT_STATE_MACHINE_CONFIG,
        MODULE.DEFAULT_ACTION_CONFIG,
        Path("configs/platform/arena_profile.yaml"),
        MODULE.DEFAULT_CALIBRATION_SPLIT,
    ):
        _write(root / relative)
    dataset_path = root / MODULE.DEFAULT_OFFLINE_ABLATION_DATASET
    _write(dataset_path, b"portable fixture dataset\n")
    ablation_path = root / MODULE.DEFAULT_OFFLINE_ABLATION_CSV
    pd.DataFrame(
        [
            {
                "dataset": MODULE.DEFAULT_OFFLINE_ABLATION_DATASET.as_posix(),
                "dataset_sha256": _sha(dataset_path),
                "sample_count": 399,
            }
        ]
    ).to_csv(ablation_path, index=False)
    _write_json(
        root / MODULE.DEFAULT_OFFLINE_ABLATION_JSON,
        {
            "schema_version": 1,
            "output": MODULE.DEFAULT_OFFLINE_ABLATION_CSV.as_posix(),
            "output_sha256": _sha(ablation_path),
            "dataset": MODULE.DEFAULT_OFFLINE_ABLATION_DATASET.as_posix(),
            "dataset_sha256": _sha(dataset_path),
            "sample_count": 399,
        },
    )
    _write_pdf(root / MODULE.DEFAULT_PAPER, 8)
    _write_pdf(root / MODULE.DEFAULT_REPORT, 31)
    _write_pdf(root / MODULE.DEFAULT_PRESENTATION_PDF, 30)
    _write_presentation(root / MODULE.DEFAULT_PRESENTATION_PPTX)
    _write(
        root / MODULE.DEFAULT_PRESENTATION_NOTES,
        (
            "阶段\uff1a`test`。\n\n"
            + "".join(f"## {number:02d}. Slide\n\nNotes.\n" for number in range(1, 31))
        ).encode(),
    )
    contact_sheet = root / MODULE.DEFAULT_PRESENTATION_CONTACT_SHEET
    contact_sheet.parent.mkdir(parents=True, exist_ok=True)
    contact = Image.new("RGB", (1200, 600), color="white")
    contact.paste((30, 100, 180), (0, 0, 600, 600))
    contact.save(contact_sheet)
    (root / MODULE.DEFAULT_CONFIG).write_text(
        "schema_version: 1\nbenchmark_id: moderate_social_navigation_v6\n",
        encoding="utf-8",
    )
    (root / MODULE.DEFAULT_CALIBRATION_SPLIT).write_text(
        "benchmark_id: moderate_social_navigation_v6\nsplit: validation\nscenarios: []\n",
        encoding="utf-8",
    )
    (root / MODULE.DEFAULT_TEST_SPLIT).write_text(
        "benchmark_id: moderate_social_navigation_v6\n"
        "split: test\nscenarios:\n"
        "  - scenario_id: fixture\n"
        "    family: doorway_bottleneck\n"
        "    density: medium\n",
        encoding="utf-8",
    )
    _write_json(
        root / MODULE.DEFAULT_CALIBRATION_REPORT,
        {"split": "validation", "status": "accepted", "passed": True},
    )

    evaluation_commit = "e" * 40
    methods = ["base", "standard", "heuristic", "bc_uniform", "pgrr"]
    checkpoints = {
        "bc_uniform": (
            MODULE.DEFAULT_UNIFORM_CHECKPOINT.as_posix(),
            _sha(root / MODULE.DEFAULT_UNIFORM_CHECKPOINT),
        ),
        "pgrr": (
            MODULE.DEFAULT_CHECKPOINT.as_posix(),
            _sha(root / MODULE.DEFAULT_CHECKPOINT),
        ),
    }
    validation_split = root / MODULE.DEFAULT_CALIBRATION_SPLIT
    evaluation_config = {
        "schema_version": 2,
        "benchmark": {
            "id": "moderate_social_navigation_v6",
            "catalog": MODULE.DEFAULT_CONFIG.as_posix(),
            "catalog_sha256": _sha(root / MODULE.DEFAULT_CONFIG),
            "calibration_split": MODULE.DEFAULT_CALIBRATION_SPLIT.as_posix(),
            "calibration_split_sha256": _sha(validation_split),
            "calibration_report": MODULE.DEFAULT_CALIBRATION_REPORT.as_posix(),
            "calibration_report_sha256": _sha(root / MODULE.DEFAULT_CALIBRATION_REPORT),
        },
        "runtime": {
            "split": "test",
            "split_manifest": MODULE.DEFAULT_TEST_SPLIT.as_posix(),
            "split_manifest_sha256": _sha(root / MODULE.DEFAULT_TEST_SPLIT),
            "episode_timeout_s": 240.0,
            "parallel_jobs": 1,
        },
        "primary_comparison": {
            "methods": methods,
            "families": ["doorway_bottleneck"],
            "densities": ["medium"],
            "repetitions_per_family_density_cell": 1,
            "expected_conditions_per_method": 1,
            "expected_episodes": 5,
        },
        "learned_baseline": {
            "source_policy": "bc_uniform",
            "checkpoint": checkpoints["bc_uniform"][0],
            "checkpoint_sha256": checkpoints["bc_uniform"][1],
        },
        "learned_method": {
            "source_policy": "pgrr",
            "checkpoint": checkpoints["pgrr"][0],
            "checkpoint_sha256": checkpoints["pgrr"][1],
        },
        "frozen_inputs": {
            "arena_profile_sha256": _sha(root / "configs/platform/arena_profile.yaml"),
            "planner_profiles_sha256": _sha(root / MODULE.DEFAULT_BASELINE_CONFIG),
            "failure_rules_sha256": _sha(root / MODULE.DEFAULT_FAILURE_CONFIG),
            "state_machine_sha256": _sha(root / MODULE.DEFAULT_STATE_MACHINE_CONFIG),
            "recovery_actions_sha256": _sha(root / MODULE.DEFAULT_ACTION_CONFIG),
            "project_commit": "resolved_and_recorded_by_runner",
        },
    }
    evaluation_path = root / MODULE.DEFAULT_EVALUATION_CONFIG
    evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    evaluation_path.write_text(yaml.safe_dump(evaluation_config), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    run_results: list[dict[str, Any]] = []
    for task_index, method in enumerate(methods):
        checkpoint_path, checkpoint_hash = checkpoints.get(method, ("", ""))
        row = {
            "task_index": task_index,
            "episode_id": f"scenario_eval_{method}_a0_dwb",
            "scenario_id": "scenario_test_seed1",
            "replicate": 0,
            "seed": 1,
            "split": "test",
            "method": method,
            "source_policy": method,
            "checkpoint_path": checkpoint_path,
            "checkpoint_sha256": checkpoint_hash,
            "project_commit": evaluation_commit,
            "timeout_s": 240.0,
            "recovery_tau_on_override": "",
        }
        rows.append(row)
        run_results.append(
            {
                "task_index": task_index,
                "episode_id": row["episode_id"],
                "scenario_id": row["scenario_id"],
                "replicate": row["replicate"],
                "method": method,
                "status": "complete",
                "checkpoint_path": checkpoint_path,
                "checkpoint_sha256": checkpoint_hash,
                "attempts": [{"outcome": "GOAL_REACHED"}],
            }
        )
    episode_frame = pd.DataFrame(rows)
    (root / MODULE.DEFAULT_EPISODE_MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    episode_frame.to_parquet(root / MODULE.DEFAULT_EPISODE_MANIFEST, index=False)
    results_frame = episode_frame.copy()
    results_frame["logical_episode_id"] = results_frame["episode_id"]
    results_frame["outcome"] = "GOAL_REACHED"
    results_frame.to_parquet(root / MODULE.DEFAULT_RESULTS, index=False)
    _write_json(
        root / MODULE.DEFAULT_REPORT_DATA,
        {
            "schema_version": 2,
            "stage": "test",
            "results_available": True,
            "results_path": MODULE.DEFAULT_RESULTS.as_posix(),
            "results_sha256": _sha(root / MODULE.DEFAULT_RESULTS),
            "statistics_path": MODULE.DEFAULT_STATISTICS.as_posix(),
            "statistics_sha256": _sha(root / MODULE.DEFAULT_STATISTICS),
            "condition_count": 1,
            "episode_count": 5,
            "valid_episode_count": 5,
            "excluded_episode_count": 0,
            "paired_comparisons": [
                {"comparator": comparator, "endpoint": endpoint}
                for comparator in ("base", "standard", "heuristic", "bc_uniform")
                for endpoint in ("goal_reached", "collision", "timeout")
            ],
            "author_alias": "Charles Chen",
        },
    )
    _write_json(
        root / MODULE.DEFAULT_RUN_MANIFEST,
        {
            "schema_version": 1,
            "run_id": "1" * 12,
            "project_commit": evaluation_commit,
            "split": "test",
            "split_manifest": MODULE.DEFAULT_TEST_SPLIT.as_posix(),
            "split_manifest_sha256": _sha(root / MODULE.DEFAULT_TEST_SPLIT),
            "episode_manifest": MODULE.DEFAULT_EPISODE_MANIFEST.as_posix(),
            "timeout_s": 240.0,
            "requested_jobs": 1,
            "effective_jobs": 1,
            "recovery_tau_on_override": "",
            "methods": methods,
            "high_density_methods": [],
            "method_checkpoints": {
                method: {"path": path, "sha256": digest}
                for method, (path, digest) in checkpoints.items()
            },
            "expected_task_count": 5,
            "completed_task_count": 5,
            "worker_errors": [],
            "results": run_results,
        },
    )
    _write(root / "paper/sections/method.tex", b"section\n")
    for name in MODULE.EXPECTED_FIGURES:
        _write(root / MODULE.DEFAULT_FIGURES_DIR / name, b"%PDF figure\n")
        _write(root / MODULE.DEFAULT_OUTPUT_FIGURES_DIR / name, b"%PDF figure\n")
    for name in MODULE.EXPECTED_TABLES:
        _write(root / MODULE.DEFAULT_TABLES_DIR / name, b"table\n")
        _write(root / MODULE.DEFAULT_OUTPUT_TABLES_DIR / name, b"table\n")
    _write_video(root / MODULE.DEFAULT_VIDEO)
    _write_pdf(root / MODULE.DEFAULT_MEDIA_KEYFRAMES_PDF, 1)
    keyframes = root / MODULE.DEFAULT_MEDIA_KEYFRAMES_PNG
    keyframes.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 200), color=(40, 120, 180)).save(keyframes)


def _set_successful_infrastructure_retry(root: Path, *, task_index: int, attempt: int) -> str:
    assert attempt in {1, 2}
    episode_path = root / MODULE.DEFAULT_EPISODE_MANIFEST
    results_path = root / MODULE.DEFAULT_RESULTS
    run_path = root / MODULE.DEFAULT_RUN_MANIFEST

    episode_frame = pd.read_parquet(episode_path)
    logical_id = str(
        episode_frame.loc[episode_frame["task_index"] == task_index, "episode_id"].item()
    )
    assert logical_id.endswith("_a0_dwb")
    episode_stem = logical_id.removesuffix("_a0_dwb")
    physical_id = f"{episode_stem}_a{attempt}_dwb"

    results_frame = pd.read_parquet(results_path)
    selected = results_frame["task_index"] == task_index
    results_frame.loc[selected, "logical_episode_id"] = logical_id
    results_frame.loc[selected, "episode_id"] = physical_id
    results_frame.to_parquet(results_path, index=False)
    report_data_path = root / MODULE.DEFAULT_REPORT_DATA
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    report_data["results_sha256"] = _sha(results_path)
    _write_json(report_data_path, report_data)

    run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
    run_result = next(
        record for record in run_manifest["results"] if record["task_index"] == task_index
    )
    run_result["episode_id"] = physical_id
    run_result["attempts"] = [
        {
            "attempt": index,
            "episode_id": f"{episode_stem}_a{index}_dwb",
            "outcome": "INVALID_RESET" if index < attempt else "GOAL_REACHED",
        }
        for index in range(attempt + 1)
    ]
    _write_json(run_path, run_manifest)
    return physical_id


def _complete_runtime_capture(root: Path) -> None:
    source = root / MODULE.OPTIONAL_RUNTIME_SCREENSHOT_SOURCE
    paper = root / MODULE.OPTIONAL_RUNTIME_SCREENSHOT
    source.parent.mkdir(parents=True, exist_ok=True)
    paper.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), color=(20, 90, 140)).save(source)
    paper.write_bytes(source.read_bytes())
    scenario_metadata = {
        "scenario_id": "doorway_medium_validation",
        "family": "doorway_bottleneck",
        "density": "medium",
        "seed": 17,
        "split": "validation",
    }
    scenario = root / "scenarios/generated/runtime_capture.json"
    _write_json(scenario, {"ramp_metadata": scenario_metadata})
    _write_json(
        root / MODULE.OPTIONAL_RUNTIME_CAPTURE_METADATA,
        {
            "artifact_type": "real_arena_gazebo_gui_screenshot",
            "capture_backend": "PyQt5.QScreen.grabWindow(X11 window)",
            "capture_target": "Gazebo GUI window",
            "dimensions": {"width_px": 800, "height_px": 600},
            "episode_id": "runtime_capture_fixture",
            "episode_outcome": "GOAL_REACHED",
            "git_commit": "c" * 40,
            "arena_commit": "d" * 40,
            "arena_image_id": "sha256:" + "a" * 64,
            "launch_profile": {
                "simulator": "gazebo",
                "headless": 0,
                "local_planner": "dwb",
            },
            "scenario": {"path": "scenarios/generated/runtime_capture.json", **scenario_metadata},
            "artifacts": {
                "screenshot": MODULE.OPTIONAL_RUNTIME_SCREENSHOT_SOURCE.as_posix(),
                "paper_copy": MODULE.OPTIONAL_RUNTIME_SCREENSHOT.as_posix(),
                "screenshot_sha256": _sha(source),
            },
            "window": {"title": "Gazebo"},
            "camera_framing": {
                "framing": "scenario_midpoint_oblique",
                "transport_service": "/gui/move_to/pose",
            },
            "visual_validation": {
                "scene_viewport_grayscale_stddev": 25.0,
                "scene_viewport_unique_colors": 500,
            },
        },
    )


def test_manifest_has_only_relative_checksummed_artifacts(tmp_path: Path) -> None:
    assert MODULE.DEFAULT_CONFIG == Path("configs/experiments/scenario_catalog_moderate_v6.yaml")
    assert MODULE.DEFAULT_TEST_SPLIT == Path("scenarios/splits/moderate_v6_test.yaml")
    assert MODULE.DEFAULT_CALIBRATION_REPORT == Path(
        "outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json"
    )
    _complete_fixture(tmp_path)

    payload = MODULE.build_manifest(
        tmp_path,
        generation_command="scripts/reproduce_paper.sh",
        generated_at="2026-08-04T12:00:00+00:00",
        project_commit="a" * 40,
        git_dirty=False,
    )

    assert payload["schema_version"] == 2
    assert payload["evaluation_commit"] == "e" * 40
    assert payload["artifact_generation_commit"] == "a" * 40
    assert payload["git_worktree_dirty"] is False
    assert payload["release"] is False
    assert payload["evaluation_provenance"]["run_id"] == "1" * 12
    assert payload["category_counts"]["figure"] == len(MODULE.EXPECTED_FIGURES)
    assert payload["category_counts"]["table"] == len(MODULE.EXPECTED_TABLES)
    assert payload["category_counts"]["checkpoint"] == 2
    assert payload["category_counts"]["video"] == 1
    assert payload["category_counts"]["runtime_keyframe"] == 2
    assert payload["category_counts"]["technical_report"] == 1
    assert payload["category_counts"]["presentation"] == 2
    assert payload["category_counts"]["offline_ablation_dataset"] == 1
    assert payload["document_pages"] == {
        MODULE.DEFAULT_PAPER.as_posix(): 8,
        MODULE.DEFAULT_REPORT.as_posix(): 31,
        MODULE.DEFAULT_PRESENTATION_PDF.as_posix(): 30,
        MODULE.DEFAULT_MEDIA_KEYFRAMES_PDF.as_posix(): 1,
    }
    assert payload["video_metadata"]["codec"] == "h264"
    assert payload["video_metadata"]["frame_count"] > 0
    assert payload["video_metadata"]["duration_s"] > 0.0
    assert payload["artifact_count"] == len(payload["artifacts"])
    paths = {record["path"] for record in payload["artifacts"]}
    assert MODULE.DEFAULT_PAPER.as_posix() in paths
    assert all(not Path(path).is_absolute() for path in paths)
    checkpoint = tmp_path / MODULE.DEFAULT_CHECKPOINT
    record = next(
        item
        for item in payload["artifacts"]
        if item["path"] == MODULE.DEFAULT_CHECKPOINT.as_posix()
    )
    assert record["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()


def test_validate_only_comparison_accepts_candidate_metadata_differences(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    _complete_runtime_capture(tmp_path)
    candidate = MODULE.build_manifest(
        tmp_path,
        generated_at="2026-08-06T00:00:00+00:00",
        project_commit="a" * 40,
        git_dirty=True,
        release=False,
    )
    published = tmp_path / MODULE.DEFAULT_OUTPUT
    _write_json(published, candidate)
    current = MODULE.build_manifest(
        tmp_path,
        generated_at="2026-08-07T00:00:00+00:00",
        project_commit="b" * 40,
        git_dirty=False,
        release=True,
    )

    MODULE._validate_existing_manifest(published, current)


def test_validate_only_comparison_rejects_tampered_artifact_record(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _complete_runtime_capture(tmp_path)
    candidate = MODULE.build_manifest(
        tmp_path,
        project_commit="a" * 40,
        git_dirty=True,
    )
    candidate["artifacts"][0]["sha256"] = "0" * 64
    published = tmp_path / MODULE.DEFAULT_OUTPUT
    _write_json(published, candidate)
    current = MODULE.build_manifest(
        tmp_path,
        project_commit="b" * 40,
        git_dirty=False,
        release=True,
    )

    with pytest.raises(MODULE.ArtifactError, match="stale or tampered"):
        MODULE._validate_existing_manifest(published, current)


def test_validate_only_cli_reads_candidate_and_never_rewrites_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_fixture(tmp_path)
    _complete_runtime_capture(tmp_path)
    candidate = MODULE.build_manifest(
        tmp_path,
        generated_at="2026-08-06T00:00:00+00:00",
        project_commit="a" * 40,
        git_dirty=True,
    )
    published = tmp_path / MODULE.DEFAULT_OUTPUT
    _write_json(published, candidate)
    original = published.read_bytes()
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "_git_commit", lambda _: "b" * 40)
    monkeypatch.setattr(MODULE, "_git_is_dirty", lambda _: False)

    assert MODULE.main(["--release", "--validate-only"]) == 0
    assert published.read_bytes() == original

    tampered = json.loads(published.read_text(encoding="utf-8"))
    tampered["category_counts"]["video"] = 99
    _write_json(published, tampered)
    assert MODULE.main(["--release", "--validate-only"]) == 2


@pytest.mark.parametrize("attempt", [1, 2])
def test_manifest_accepts_valid_infrastructure_retry_identity_chain(
    tmp_path: Path,
    attempt: int,
) -> None:
    _complete_fixture(tmp_path)
    physical_id = _set_successful_infrastructure_retry(
        tmp_path,
        task_index=4,
        attempt=attempt,
    )

    payload = MODULE.build_manifest(
        tmp_path,
        project_commit="a" * 40,
        git_dirty=False,
    )

    episode_frame = pd.read_parquet(tmp_path / MODULE.DEFAULT_EPISODE_MANIFEST)
    results_frame = pd.read_parquet(tmp_path / MODULE.DEFAULT_RESULTS)
    run_manifest = json.loads((tmp_path / MODULE.DEFAULT_RUN_MANIFEST).read_text(encoding="utf-8"))
    logical_id = str(episode_frame.loc[episode_frame["task_index"] == 4, "episode_id"].item())
    result = results_frame.loc[results_frame["task_index"] == 4].iloc[0]
    run_result = next(record for record in run_manifest["results"] if record["task_index"] == 4)
    assert logical_id.endswith("_a0_dwb")
    assert result["logical_episode_id"] == logical_id
    assert result["episode_id"] == physical_id
    assert run_result["episode_id"] == physical_id
    assert payload["evaluation_provenance"]["run_id"] == "1" * 12


def test_manifest_rejects_retry_physical_id_not_recorded_by_runner(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _set_successful_infrastructure_retry(tmp_path, task_index=4, attempt=2)
    results_path = tmp_path / MODULE.DEFAULT_RESULTS
    results_frame = pd.read_parquet(results_path)
    selected = results_frame["task_index"] == 4
    results_frame.loc[selected, "episode_id"] = str(
        results_frame.loc[selected, "episode_id"].item()
    ).replace("_a2_dwb", "_a1_dwb")
    results_frame.to_parquet(results_path, index=False)

    with pytest.raises(MODULE.ArtifactError, match="physical episode_id disagree"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="a" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_retry_logical_id_not_in_episode_manifest(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _set_successful_infrastructure_retry(tmp_path, task_index=4, attempt=1)
    results_path = tmp_path / MODULE.DEFAULT_RESULTS
    results_frame = pd.read_parquet(results_path)
    results_frame.loc[results_frame["task_index"] == 4, "logical_episode_id"] = (
        "wrong_logical_episode_a0_dwb"
    )
    results_frame.to_parquet(results_path, index=False)

    with pytest.raises(MODULE.ArtifactError, match="logical_episode_id disagree"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="a" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_retry_with_changed_run_identity(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _set_successful_infrastructure_retry(tmp_path, task_index=4, attempt=1)
    run_path = tmp_path / MODULE.DEFAULT_RUN_MANIFEST
    run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
    run_result = next(record for record in run_manifest["results"] if record["task_index"] == 4)
    run_result["replicate"] = 99
    _write_json(run_path, run_manifest)

    with pytest.raises(MODULE.ArtifactError, match="episode manifest identity"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="a" * 40,
            git_dirty=False,
        )


def test_manifest_fails_closed_when_a_required_artifact_is_missing(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    (tmp_path / MODULE.DEFAULT_PAPER).unlink()

    with pytest.raises(MODULE.ArtifactError, match="paper PDF"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_non_test_report_data(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    report_data_path = tmp_path / MODULE.DEFAULT_REPORT_DATA
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    report_data["stage"] = "validation"
    _write_json(report_data_path, report_data)

    with pytest.raises(MODULE.ArtifactError, match="locked test stage"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_report_bound_to_a_different_result_hash(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    report_data_path = tmp_path / MODULE.DEFAULT_REPORT_DATA
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    report_data["results_sha256"] = "0" * 64
    _write_json(report_data_path, report_data)

    with pytest.raises(MODULE.ArtifactError, match="hash disagrees"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_report_bound_to_different_statistics(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    report_data_path = tmp_path / MODULE.DEFAULT_REPORT_DATA
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    report_data["statistics_sha256"] = "0" * 64
    _write_json(report_data_path, report_data)

    with pytest.raises(MODULE.ArtifactError, match="pairwise statistics"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


@pytest.mark.parametrize("pages", [29, 41])
def test_manifest_rejects_report_outside_page_range(tmp_path: Path, pages: int) -> None:
    _complete_fixture(tmp_path)
    _write_pdf(tmp_path / MODULE.DEFAULT_REPORT, pages)

    with pytest.raises(MODULE.ArtifactError, match="30--40 pages"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


@pytest.mark.parametrize("pages", [30, 40])
def test_manifest_accepts_report_page_range_boundaries(tmp_path: Path, pages: int) -> None:
    _complete_fixture(tmp_path)
    _write_pdf(tmp_path / MODULE.DEFAULT_REPORT, pages)

    payload = MODULE.build_manifest(
        tmp_path,
        project_commit="b" * 40,
        git_dirty=False,
    )
    assert payload["document_pages"][MODULE.DEFAULT_REPORT.as_posix()] == pages


def test_manifest_rejects_incomplete_presentation(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _write_presentation(tmp_path / MODULE.DEFAULT_PRESENTATION_PPTX, slides=29)

    with pytest.raises(MODULE.ArtifactError, match="exactly 30 slides"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_presentation_last_modified_by_mismatch(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    pptx = tmp_path / MODULE.DEFAULT_PRESENTATION_PPTX
    _write_presentation(pptx, modified_by="Different Author")

    with pytest.raises(MODULE.ArtifactError, match="creator and lastModifiedBy"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_blank_presentation_contact_sheet(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    Image.new("RGB", (1200, 600), color="white").save(
        tmp_path / MODULE.DEFAULT_PRESENTATION_CONTACT_SHEET
    )

    with pytest.raises(MODULE.ArtifactError, match="insufficient visual contrast"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_corrupt_keyframe_png(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _write(tmp_path / MODULE.DEFAULT_MEDIA_KEYFRAMES_PNG, b"not a png")

    with pytest.raises(MODULE.ArtifactError, match="telemetry keyframes PNG"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_corrupt_telemetry_video(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _write(tmp_path / MODULE.DEFAULT_VIDEO, b"not an mp4")

    with pytest.raises(MODULE.ArtifactError, match="cannot be decoded"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_offline_ablation_dataset_hash_mismatch(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    dataset = tmp_path / MODULE.DEFAULT_OFFLINE_ABLATION_DATASET
    dataset.write_bytes(dataset.read_bytes() + b"tamper")

    with pytest.raises(MODULE.ArtifactError, match="dataset hash disagrees"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_requires_a_final_telemetry_video(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    (tmp_path / MODULE.DEFAULT_VIDEO).unlink()

    with pytest.raises(MODULE.ArtifactError, match="final telemetry video"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="c" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_artifacts_outside_project(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    outside = tmp_path.parent / "outside.pdf"
    _write(outside)

    with pytest.raises(MODULE.ArtifactError, match="inside the project root"):
        MODULE.build_manifest(
            tmp_path,
            paper_path=outside,
            project_commit="d" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_test_split_calibration_report(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _write(
        tmp_path / MODULE.DEFAULT_CALIBRATION_REPORT,
        (json.dumps({"split": "test", "status": "rejected", "passed": False}) + "\n").encode(),
    )
    evaluation_path = tmp_path / MODULE.DEFAULT_EVALUATION_CONFIG
    evaluation = yaml.safe_load(evaluation_path.read_text(encoding="utf-8"))
    evaluation["benchmark"]["calibration_report_sha256"] = _sha(
        tmp_path / MODULE.DEFAULT_CALIBRATION_REPORT
    )
    evaluation_path.write_text(yaml.safe_dump(evaluation), encoding="utf-8")

    with pytest.raises(MODULE.ArtifactError, match="validation-only"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="e" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_calibration_report_hash_mismatch(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    report = tmp_path / MODULE.DEFAULT_CALIBRATION_REPORT
    report.write_bytes(report.read_bytes() + b" ")

    with pytest.raises(MODULE.ArtifactError, match="hash mismatch"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="e" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_non_v6_evaluation_identity(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    evaluation_path = tmp_path / MODULE.DEFAULT_EVALUATION_CONFIG
    evaluation = yaml.safe_load(evaluation_path.read_text(encoding="utf-8"))
    evaluation["benchmark"]["id"] = "moderate_social_navigation_v5"
    evaluation_path.write_text(yaml.safe_dump(evaluation), encoding="utf-8")

    with pytest.raises(MODULE.ArtifactError, match="moderate_social_navigation_v6"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="e" * 40,
            git_dirty=True,
        )


def test_manifest_requires_runtime_capture_metadata_when_screenshot_exists(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    _write(tmp_path / MODULE.OPTIONAL_RUNTIME_SCREENSHOT, b"PNG screenshot\n")

    with pytest.raises(MODULE.ArtifactError, match="must all exist or all be absent"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="f" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_results_from_a_different_evaluation_commit(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    results = pd.read_parquet(tmp_path / MODULE.DEFAULT_RESULTS)
    results["project_commit"] = "a" * 40
    results.to_parquet(tmp_path / MODULE.DEFAULT_RESULTS, index=False)

    with pytest.raises(MODULE.ArtifactError, match="project_commit disagrees"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_run_checkpoint_that_disagrees_with_final_config(
    tmp_path: Path,
) -> None:
    _complete_fixture(tmp_path)
    run_path = tmp_path / MODULE.DEFAULT_RUN_MANIFEST
    run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
    run_manifest["method_checkpoints"]["pgrr"]["sha256"] = "0" * 64
    _write_json(run_path, run_manifest)

    with pytest.raises(MODULE.ArtifactError, match="pgrr checkpoint provenance disagrees"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_manifest_rejects_run_split_that_disagrees_with_final_config(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    run_path = tmp_path / MODULE.DEFAULT_RUN_MANIFEST
    run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
    run_manifest["split_manifest_sha256"] = "0" * 64
    _write_json(run_path, run_manifest)

    with pytest.raises(MODULE.ArtifactError, match="test split hash disagrees"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
        )


def test_release_manifest_rejects_a_dirty_worktree(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)

    with pytest.raises(MODULE.ArtifactError, match="clean Git worktree"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=True,
            release=True,
        )


def test_release_manifest_requires_and_validates_real_runtime_capture(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)

    with pytest.raises(MODULE.ArtifactError, match="verified real Gazebo"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
            release=True,
        )

    _complete_runtime_capture(tmp_path)
    payload = MODULE.build_manifest(
        tmp_path,
        project_commit="b" * 40,
        git_dirty=False,
        release=True,
    )
    assert payload["release"] is True
    assert payload["category_counts"]["runtime_screenshot"] == 1
    assert payload["category_counts"]["runtime_screenshot_source"] == 1
    assert payload["category_counts"]["runtime_capture_metadata"] == 1


def test_runtime_capture_metadata_rejects_a_test_scenario(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    _complete_runtime_capture(tmp_path)
    metadata_path = tmp_path / MODULE.OPTIONAL_RUNTIME_CAPTURE_METADATA
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["scenario"]["split"] = "test"
    scenario_path = tmp_path / metadata["scenario"]["path"]
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["ramp_metadata"]["split"] = "test"
    _write_json(metadata_path, metadata)
    _write_json(scenario_path, scenario)

    with pytest.raises(MODULE.ArtifactError, match="held-out test"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=False,
            release=True,
        )
