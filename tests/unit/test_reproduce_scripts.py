from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_reproduction_scripts_are_executable_and_relocatable() -> None:
    for name in ("reproduce_small.sh", "reproduce_paper.sh"):
        path = ROOT / "scripts" / name
        source = _source(name)
        assert os.access(path, os.X_OK)
        assert "BASH_SOURCE[0]" in source
        assert "SCRIPT_DIR}/.." in source
        assert "/home/" not in source
        assert "${HOME}/RAMP" not in source
        assert "rm -rf" not in source


def test_small_reproduction_runs_offline_checks_and_has_a_safe_final_gate() -> None:
    source = _source("reproduce_small.sh")
    assert "pytest -q" in source
    assert "offline_policy_ablation.py" in source
    assert "outputs/smoke/offline_policy_ablation.csv" in source
    assert "--output outputs/final/offline_policy_ablation.csv" not in source
    assert "episode_manifest.parquet" in source
    assert "run_manifest.json" in source
    assert "SKIP final paper chain" in source
    assert "BOOTSTRAP_SEED=20260804" in source
    assert '--bootstrap-seed "${BOOTSTRAP_SEED}"' in source
    assert "collect_results.py" in source
    assert "make_figures.py" in source
    assert "make_tables.py" in source
    assert "build_paper.sh" in source


def test_make_statistics_uses_the_frozen_collector_contract() -> None:
    source = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = source.split("statistics:", maxsplit=1)[1].split("figures:", maxsplit=1)[0]
    assert "collect_results.py" in target
    assert '--manifest "$(MODERATE_ANALYSIS_DIR)/episode_manifest.parquet"' in target
    assert '--run-manifest "$(MODERATE_ANALYSIS_DIR)/run_manifest.json"' in target
    assert '--results "$(MODERATE_RESULTS)"' in target
    assert '--summary "$(MODERATE_ANALYSIS_DIR)/collector_summary.csv"' in target
    assert '--statistics "$(MODERATE_ANALYSIS_DIR)/collector_statistics.json"' in target
    assert "summarize_moderate.py" in target
    assert "--methods $(MODERATE_METHODS)" in target
    assert '--main-method "$(MODERATE_MAIN_METHOD)"' in target
    assert '--reference-method "$(MODERATE_REFERENCE_METHOD)"' in target
    assert '--bootstrap-seed "$(BOOTSTRAP_SEED)"' in target
    assert "BOOTSTRAP_SEED ?= 20260804" in source


def test_paper_development_rebuild_uses_published_inputs_by_default() -> None:
    source = _source("reproduce_paper.sh")
    assert "PGRR_RELEASE_MODE:-0" in source
    assert "PGRR_RECOLLECT_RAW:-0" in source
    assert "collect_results.py" in source
    assert "summarize_moderate.py" in source
    assert "failure_analysis.py" in source
    assert "render_episode_media.py" in source
    assert "offline_policy_ablation.py" in source
    assert 'OFFLINE_ABLATION="${MODERATE_ANALYSIS_DIR}/offline_policy_ablation.csv"' in source
    assert "outputs/final/offline_policy_ablation.csv" not in source
    assert "make_method_figures.py" in source
    assert "make_moderate_figures.py" in source
    assert "make_moderate_tables.py" in source
    assert "make_figures.py" not in source
    assert "scripts/paper/make_tables.py" not in source
    assert '--ablation "${OFFLINE_ABLATION}"' in source
    assert "build_paper.sh" in source
    assert "build_artifact_manifest.py" in source
    assert "outputs/moderate/final" in source
    assert "MODERATE_EXPECTED_CONDITIONS:-120" in source
    assert "configs/final/ei_gazebo.yaml" in source
    assert "scenario_catalog_moderate_v6.yaml" in source
    assert "moderate_v6_test.yaml" in source
    assert "outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json" in source
    assert "moderate_v5" not in source
    assert "METHODS=(base standard heuristic bc_uniform pgrr)" in source
    assert "--main-method pgrr" in source
    assert "--bootstrap-seed 20260804" in source
    assert '--test-split "${MODERATE_TEST_SPLIT}"' in source
    assert '--evaluation-config "${FINAL_EVALUATION_CONFIG}"' in source
    assert '--calibration-report "${MODERATE_CALIBRATION_REPORT}"' in source
    assert "git status --porcelain --untracked-files=all" in source
    assert "PGRR_RECOLLECT_RAW=1 requires data/raw" in source
    assert '[[ "${MODERATE_ANALYSIS_DIR}" != "outputs/moderate/final" ]]' in source
    assert '[[ "${MODERATE_EXPECTED_CONDITIONS}" != "120" ]]' in source
    assert "REPORT_STAGE=test" in source
    assert 'REPORT_STATISTICS="${PROJECT_ROOT}/${STATISTICS}"' in source
    assert 'REPORT_MATCHED_EVIDENCE="${PROJECT_ROOT}/${MATCHED_EVIDENCE}"' in source
    assert "REPORT_EXPECTED_CONDITIONS=120" in source
    assert "scripts/report/build_report.sh" in source
    assert "scripts/presentation/build_deck.py" in source
    assert "scripts/presentation/render_pdf.sh" in source
    assert "presentation/contact_sheet.png" in source
    assert '--report "${REPORT_PDF}"' in source
    assert '--presentation-pptx "${PRESENTATION_PPTX}"' in source
    assert '--media-keyframes-pdf "${FINAL_KEYFRAMES_PDF}"' in source
    assert '--matched-evidence "${MATCHED_EVIDENCE}"' in source
    assert '--matched-trajectory "${MATCHED_TRAJECTORY}"' in source
    assert '--matched-recovery-timeline "${MATCHED_TIMELINE}"' in source
    assert 'require_pdf_pages "paper/main.pdf" 8' in source
    assert 'require_pdf_page_range "${REPORT_PDF}" 30 40' in source
    assert 'require_pdf_pages "${PRESENTATION_PDF}" 30' in source
    assert "DEVELOPMENT REBUILD PASS" in source
    assert "not a privacy/release PASS" in source
    assert "run_experiment.py" not in source
    assert "run_baseline.py" not in source
    assert "smoke_arena.sh" not in source

    stages = (
        "make_method_figures.py",
        "make_moderate_figures.py",
        "make_moderate_tables.py",
        "build_paper.sh",
        "scripts/report/build_report.sh",
        "scripts/presentation/build_deck.py",
        "scripts/presentation/render_pdf.sh",
        'offline "${manifest_command[@]}"',
    )
    offsets = [source.index(stage) for stage in stages[:-1]] + [source.rindex(stages[-1])]
    assert offsets == sorted(offsets)


def test_release_mode_validates_before_any_generation_and_exits() -> None:
    source = _source("reproduce_paper.sh")
    release_block = source.split('if [[ "${PGRR_RELEASE_MODE}" == "1" ]]; then', maxsplit=1)[
        1
    ].split("\nfi\n", maxsplit=1)[0]
    manifest_call = 'offline "${manifest_command[@]}" --release --validate-only'
    privacy_call = "offline python scripts/bootstrap/privacy_audit.py"
    assert manifest_call in release_block
    assert privacy_call in release_block
    assert release_block.index(manifest_call) < release_block.index(privacy_call)
    assert release_block.index(privacy_call) < release_block.index("exit 0")
    assert "--all-files" not in release_block
    for forbidden in (
        "collect_results.py",
        "summarize_moderate.py",
        "make_method_figures.py",
        "make_moderate_tables.py",
        "build_paper.sh",
        "build_report.sh",
        "build_deck.py",
    ):
        assert forbidden not in release_block


def test_raw_recollection_is_explicitly_guarded() -> None:
    source = _source("reproduce_paper.sh")
    raw_tail = source.split('if [[ "${PGRR_RECOLLECT_RAW}" == "1" ]]; then', maxsplit=1)[1]
    raw_block, published_block = raw_tail.split("\nelse\n", maxsplit=1)
    for required in (
        "offline_policy_ablation.py",
        "collect_results.py",
        "summarize_moderate.py",
        "failure_analysis.py",
        "render_episode_media.py",
        "--raw-dir data/raw",
        "--matched-final",
        '--evidence-output "${MATCHED_EVIDENCE}"',
    ):
        assert required in raw_block
    assert "using published result/statistics/failure/media artifacts" in published_block
    for required in ("${MATCHED_EVIDENCE}", "${MATCHED_TRAJECTORY}", "${MATCHED_TIMELINE}"):
        assert required in published_block


def test_clean_git_archive_contains_portable_offline_dataset(tmp_path: Path) -> None:
    """A clean source archive retains the no-raw rebuild inputs."""

    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    (repository / "data/interim").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/reproduce_paper.sh", repository / "scripts/reproduce_paper.sh")
    dataset = Path("data/interim/multiscenario_safety_aligned_validation.h5")
    shutil.copy2(ROOT / dataset, repository / dataset)
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Charles Chen",
            "-c",
            "user.email=charles.chen@example.invalid",
            "add",
            ".",
        ],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Charles Chen",
            "-c",
            "user.email=charles.chen@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as bundle:
        member = bundle.getmember(dataset.as_posix())
        assert member.size > 1_000_000
        script_member = bundle.extractfile("scripts/reproduce_paper.sh")
        assert script_member is not None
        source = script_member.read().decode("utf-8")
    assert "PGRR_RECOLLECT_RAW:-0" in source
    assert "using published result/statistics/failure/media artifacts" in source
    assert source.index('if [[ "${PGRR_RECOLLECT_RAW}" == "1" ]]') < source.index(
        "--raw-dir data/raw"
    )
    assert "scripts/paper/build_paper.sh" in source
    assert "scripts/report/build_report.sh" in source
    assert "scripts/presentation/build_deck.py" in source


def test_paper_build_checks_overfull_boxes_and_embedded_fonts() -> None:
    source = (ROOT / "scripts" / "paper" / "build_paper.sh").read_text(encoding="utf-8")
    assert "moderate_result_macros.tex" in source
    assert "moderate_outcomes_and_density.pdf" in source
    assert "make_figures.py" not in source
    assert "make_tables.py" not in source
    assert "pdfinfo main.pdf" in source
    assert '[[ "${paper_pages}" != "8" ]]' in source
    assert "conference paper must contain exactly 8 pages" in source
    assert "grep -Fq 'Overfull \\hbox' main.log" in source
    assert 'NR > 2 && $4 == "no"' in source
    assert "$(NF-4)" not in source
