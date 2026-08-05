#!/usr/bin/env python3
"""Build a checksummed manifest for the reproducible paper artifacts.

All stored paths are relative to the repository root derived from this file.
The command fails closed when a declared publication artifact is missing or
empty; it never invents results or silently omits an artifact category.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG = Path("configs/experiments/scenario_catalog_moderate_v4.yaml")
DEFAULT_BASELINE_CONFIG = Path("configs/planner/baselines.yaml")
DEFAULT_UNIFORM_CHECKPOINT = Path("checkpoints/bc/uniform_scenario/best.onnx")
DEFAULT_CHECKPOINT = Path("checkpoints/dagger/coverage_safety_aligned/best.onnx")
DEFAULT_RESULTS = Path("outputs/moderate/final/results.parquet")
DEFAULT_SUMMARY = Path("outputs/moderate/final/summary.csv")
DEFAULT_STATISTICS = Path("outputs/moderate/final/pairwise_statistics.json")
DEFAULT_CALIBRATION_REPORT = Path("outputs/moderate/final/calibration_report.json")
DEFAULT_FAILURE_ANALYSIS = Path("outputs/moderate/final/failure_analysis.md")
DEFAULT_EPISODE_MANIFEST = Path("outputs/moderate/final/episode_manifest.parquet")
DEFAULT_RUN_MANIFEST = Path("outputs/moderate/final/run_manifest.json")
DEFAULT_OFFLINE_ABLATION_CSV = Path("outputs/final/offline_policy_ablation.csv")
DEFAULT_OFFLINE_ABLATION_JSON = Path("outputs/final/offline_policy_ablation.json")
DEFAULT_FIGURES_DIR = Path("paper/figures")
DEFAULT_TABLES_DIR = Path("paper/generated")
DEFAULT_OUTPUT_FIGURES_DIR = Path("outputs/figures")
DEFAULT_OUTPUT_TABLES_DIR = Path("outputs/tables")
DEFAULT_VIDEOS_DIR = Path("outputs/videos")
DEFAULT_PAPER = Path("paper/main.pdf")
DEFAULT_MAIN_TEX = Path("paper/main.tex")
DEFAULT_REFERENCES = Path("paper/references.bib")
DEFAULT_CLAIM_MATRIX = Path("paper/claim_evidence_matrix.md")
DEFAULT_ENVIRONMENT_LOCK = Path("environment.lock.yml")
DEFAULT_REQUIREMENTS_LOCK = Path("requirements-offline.lock.txt")
DEFAULT_ARENA_LOCK = Path("third_party/arena_commits.lock")
DEFAULT_DEPENDENCY_MANIFEST = Path("third_party/dependency_manifest.md")
DEFAULT_TEST_SPLIT = Path("scenarios/splits/moderate_v4_test.yaml")
DEFAULT_FAILURE_CONFIG = Path("configs/failure/rules.yaml")
DEFAULT_STATE_MACHINE_CONFIG = Path("configs/failure/recovery_state_machine.yaml")
DEFAULT_ACTION_CONFIG = Path("configs/planner/recovery_actions.yaml")
DEFAULT_OUTPUT = Path("outputs/moderate/final/artifact_manifest.json")

EXPECTED_FIGURES = (
    "system_architecture.pdf",
    "action_space_expert.pdf",
    "moderate_outcomes_and_density.pdf",
    "moderate_family_success.pdf",
    "moderate_paired_effects.pdf",
    "moderate_safety_efficiency.pdf",
)
EXPECTED_TABLES = (
    "offline_ablation.tex",
    "moderate_main_results.tex",
    "moderate_density_results.tex",
    "moderate_recovery_metrics.tex",
    "moderate_pairwise_statistics.tex",
    "moderate_result_macros.tex",
)


class ArtifactError(RuntimeError):
    """Raised when publication artifacts or their provenance are invalid."""


def sha256_file(path: Path) -> str:
    """Return a streaming SHA256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside_root(project_root: Path, value: Path, *, label: str) -> Path:
    candidate = value if value.is_absolute() else project_root / value
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ArtifactError(f"{label} must be inside the project root: {value}") from error
    return resolved


def _require_file(project_root: Path, value: Path, *, label: str) -> Path:
    path = _inside_root(project_root, value, label=label)
    if not path.is_file():
        raise ArtifactError(f"missing required {label}: {path.relative_to(project_root)}")
    if path.stat().st_size <= 0:
        raise ArtifactError(f"empty required {label}: {path.relative_to(project_root)}")
    return path


def _git_commit(project_root: Path) -> str:
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError("cannot resolve the repository Git commit") from error
    if len(commit) != 40:
        raise ArtifactError(f"unexpected Git commit value: {commit!r}")
    return commit


def _git_is_dirty(project_root: Path) -> bool:
    try:
        status = subprocess.check_output(
            ["git", "-C", str(project_root), "status", "--porcelain"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError("cannot inspect the repository Git status") from error
    return bool(status.strip())


def _artifact_record(project_root: Path, category: str, path: Path) -> dict[str, Any]:
    return {
        "category": category,
        "path": path.relative_to(project_root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_manifest(
    project_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    baseline_config_path: Path = DEFAULT_BASELINE_CONFIG,
    uniform_checkpoint_path: Path = DEFAULT_UNIFORM_CHECKPOINT,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    results_path: Path = DEFAULT_RESULTS,
    summary_path: Path = DEFAULT_SUMMARY,
    statistics_path: Path = DEFAULT_STATISTICS,
    calibration_report_path: Path = DEFAULT_CALIBRATION_REPORT,
    failure_analysis_path: Path = DEFAULT_FAILURE_ANALYSIS,
    episode_manifest_path: Path = DEFAULT_EPISODE_MANIFEST,
    run_manifest_path: Path = DEFAULT_RUN_MANIFEST,
    figures_dir: Path = DEFAULT_FIGURES_DIR,
    tables_dir: Path = DEFAULT_TABLES_DIR,
    videos_dir: Path = DEFAULT_VIDEOS_DIR,
    paper_path: Path = DEFAULT_PAPER,
    generation_command: str = "scripts/reproduce_paper.sh",
    generated_at: str | None = None,
    project_commit: str | None = None,
    git_dirty: bool | None = None,
) -> dict[str, Any]:
    """Validate and describe the complete paper artifact set."""

    root = project_root.resolve()
    singleton_specs = (
        ("final_config", config_path, "final configuration"),
        ("final_config", baseline_config_path, "baseline configuration"),
        ("checkpoint", uniform_checkpoint_path, "Uniform BC checkpoint"),
        ("checkpoint", checkpoint_path, "selected checkpoint"),
        ("episode_manifest", episode_manifest_path, "episode manifest"),
        ("run_manifest", run_manifest_path, "run manifest"),
        ("results", results_path, "episode results"),
        ("summary", summary_path, "result summary"),
        ("statistics", statistics_path, "statistics report"),
        (
            "calibration_report",
            calibration_report_path,
            "moderate calibration report",
        ),
        ("failure_analysis", failure_analysis_path, "failure analysis"),
        (
            "offline_ablation",
            DEFAULT_OFFLINE_ABLATION_CSV,
            "offline ablation CSV",
        ),
        (
            "offline_ablation",
            DEFAULT_OFFLINE_ABLATION_JSON,
            "offline ablation provenance",
        ),
        ("paper_source", DEFAULT_MAIN_TEX, "paper TeX source"),
        ("paper_source", DEFAULT_REFERENCES, "paper references"),
        ("claim_evidence", DEFAULT_CLAIM_MATRIX, "claim-evidence matrix"),
        ("environment_lock", DEFAULT_ENVIRONMENT_LOCK, "Conda environment lock"),
        ("environment_lock", DEFAULT_REQUIREMENTS_LOCK, "pip environment lock"),
        ("runtime_lock", DEFAULT_ARENA_LOCK, "Arena commit lock"),
        (
            "runtime_lock",
            DEFAULT_DEPENDENCY_MANIFEST,
            "runtime dependency manifest",
        ),
        ("frozen_input", DEFAULT_TEST_SPLIT, "test split"),
        ("frozen_input", DEFAULT_FAILURE_CONFIG, "failure-detector configuration"),
        (
            "frozen_input",
            DEFAULT_STATE_MACHINE_CONFIG,
            "recovery-state-machine configuration",
        ),
        ("frozen_input", DEFAULT_ACTION_CONFIG, "recovery-action configuration"),
        ("paper", paper_path, "paper PDF"),
    )
    artifacts: list[tuple[str, Path]] = []
    for category, path, label in singleton_specs:
        artifacts.append((category, _require_file(root, path, label=label)))

    resolved_figures_dir = _inside_root(root, figures_dir, label="figures directory")
    for filename in EXPECTED_FIGURES:
        artifacts.append(
            (
                "figure",
                _require_file(
                    root,
                    resolved_figures_dir / filename,
                    label=f"generated figure {filename}",
                ),
            )
        )

    resolved_tables_dir = _inside_root(root, tables_dir, label="tables directory")
    for filename in EXPECTED_TABLES:
        artifacts.append(
            (
                "table",
                _require_file(
                    root,
                    resolved_tables_dir / filename,
                    label=f"generated table {filename}",
                ),
            )
        )

    for source in sorted((root / "paper" / "sections").glob("*.tex")):
        artifacts.append(("paper_source", _require_file(root, source, label="paper section")))
    if not any(
        category == "paper_source" and path.parent.name == "sections"
        for category, path in artifacts
    ):
        raise ArtifactError("missing required paper sections: paper/sections/*.tex")

    resolved_output_figures = _inside_root(
        root, DEFAULT_OUTPUT_FIGURES_DIR, label="published figures directory"
    )
    for filename in EXPECTED_FIGURES:
        artifacts.append(
            (
                "published_figure",
                _require_file(
                    root,
                    resolved_output_figures / filename,
                    label=f"published figure {filename}",
                ),
            )
        )

    resolved_output_tables = _inside_root(
        root, DEFAULT_OUTPUT_TABLES_DIR, label="published tables directory"
    )
    for filename in EXPECTED_TABLES:
        artifacts.append(
            (
                "published_table",
                _require_file(
                    root,
                    resolved_output_tables / filename,
                    label=f"published table {filename}",
                ),
            )
        )

    resolved_videos_dir = _inside_root(root, videos_dir, label="videos directory")
    videos = sorted(path for path in resolved_videos_dir.glob("*_telemetry.mp4") if path.is_file())
    if not videos:
        raise ArtifactError(
            "missing required final telemetry video: "
            f"{resolved_videos_dir.relative_to(root)}/*_telemetry.mp4"
        )
    for video in videos:
        if video.stat().st_size <= 0:
            raise ArtifactError(f"empty required result video: {video.relative_to(root)}")
        artifacts.append(("video", video))

    for suffix in ("pdf", "png"):
        keyframes = sorted(
            path
            for path in resolved_output_figures.glob(f"*_telemetry_keyframes.{suffix}")
            if path.is_file()
        )
        if not keyframes:
            raise ArtifactError(
                "missing required final telemetry keyframes: "
                f"{resolved_output_figures.relative_to(root)}/*_telemetry_keyframes.{suffix}"
            )
        for keyframe in keyframes:
            if keyframe.stat().st_size <= 0:
                raise ArtifactError(
                    f"empty required telemetry keyframe: {keyframe.relative_to(root)}"
                )
            artifacts.append(("runtime_keyframe", keyframe))

    commit = project_commit if project_commit is not None else _git_commit(root)
    dirty = git_dirty if git_dirty is not None else _git_is_dirty(root)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    records = [_artifact_record(root, category, path) for category, path in artifacts]
    counts = Counter(str(record["category"]) for record in records)
    return {
        "schema_version": 1,
        "generated_at": timestamp,
        "generation_command": generation_command,
        "project_commit": commit,
        "git_worktree_dirty": dirty,
        "artifact_count": len(records),
        "category_counts": dict(sorted(counts.items())),
        "artifacts": records,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--baseline-config", type=Path, default=DEFAULT_BASELINE_CONFIG)
    parser.add_argument("--uniform-checkpoint", type=Path, default=DEFAULT_UNIFORM_CHECKPOINT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--statistics", type=Path, default=DEFAULT_STATISTICS)
    parser.add_argument("--calibration-report", type=Path, default=DEFAULT_CALIBRATION_REPORT)
    parser.add_argument("--failure-analysis", type=Path, default=DEFAULT_FAILURE_ANALYSIS)
    parser.add_argument("--episode-manifest", type=Path, default=DEFAULT_EPISODE_MANIFEST)
    parser.add_argument("--run-manifest", type=Path, default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES_DIR)
    parser.add_argument("--videos-dir", type=Path, default=DEFAULT_VIDEOS_DIR)
    parser.add_argument("--paper", type=Path, default=DEFAULT_PAPER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--command", default="scripts/reproduce_paper.sh")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_manifest(
            ROOT,
            config_path=args.config,
            baseline_config_path=args.baseline_config,
            uniform_checkpoint_path=args.uniform_checkpoint,
            checkpoint_path=args.checkpoint,
            results_path=args.results,
            summary_path=args.summary,
            statistics_path=args.statistics,
            calibration_report_path=args.calibration_report,
            failure_analysis_path=args.failure_analysis,
            episode_manifest_path=args.episode_manifest,
            run_manifest_path=args.run_manifest,
            figures_dir=args.figures_dir,
            tables_dir=args.tables_dir,
            videos_dir=args.videos_dir,
            paper_path=args.paper,
            generation_command=args.command,
        )
        output = _inside_root(ROOT.resolve(), args.output, label="artifact manifest output")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    except (ArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Artifact manifest PASS: {output.relative_to(ROOT)} ({payload['artifact_count']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
