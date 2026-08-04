from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import h5py
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


privacy_audit = _load_module("privacy_audit", ROOT / "scripts/bootstrap/privacy_audit.py")
label_expert = _load_module("label_expert_privacy", ROOT / "scripts/data/label_expert.py")
_load_module("make_figures", ROOT / "scripts/paper/make_figures.py")
make_tables = _load_module("make_tables_privacy", ROOT / "scripts/paper/make_tables.py")


def _private_home() -> str:
    return "/" + "home" + "/" + "diy"


def _legacy_hostname() -> str:
    return "diy" + "01"


def test_clean_tree_allows_alias_anonymous_and_placeholders(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Authors: Charles Chen and Anonymous Authors\n"
        "root=${PROJECT_ROOT}\narena=${ARENA_WS}\n"
        "contact=charles.chen@example.invalid\n",
        encoding="utf-8",
    )

    findings, count = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert count == 1
    assert findings == []
    assert privacy_audit.main([str(tmp_path), "--all-files"]) == 0


def test_text_binary_and_email_leaks_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "report.txt").write_text(
        f"root={_private_home()}/PGRR\nhostname={_legacy_hostname()}\n"
        "maintainer=" + "ramp-local" + "@" + "example.com\n",
        encoding="utf-8",
    )
    (tmp_path / "model.bin").write_bytes(
        b"\x00model metadata\x00" + _private_home().encode() + b"/checkpoint\x00"
    )

    findings, count = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert count == 2
    assert {finding.source for finding in findings} >= {"text", "binary-strings"}
    assert any(finding.rule == "non-allowlisted email address" for finding in findings)
    assert privacy_audit.main([str(tmp_path), "--all-files"]) == 1


def test_private_identifier_in_filename_is_rejected(tmp_path: Path) -> None:
    (tmp_path / f"report_{_legacy_hostname()}.txt").write_text(
        "Anonymous Authors\n", encoding="utf-8"
    )

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "path" for finding in findings)


def test_hdf5_attributes_are_audited(tmp_path: Path) -> None:
    dataset = tmp_path / "expert.h5"
    with h5py.File(dataset, "w") as handle:
        handle.attrs["source_jsonl"] = _private_home() + "/raw/episode.jsonl"

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "hdf5-attribute" for finding in findings)
    assert any("source_jsonl" in finding.rule for finding in findings)


def test_default_git_surface_includes_untracked_but_not_ignored(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.bin\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Anonymous Authors\n", encoding="utf-8")
    (tmp_path / "ignored.bin").write_text(_private_home(), encoding="utf-8")

    findings, count = privacy_audit.scan_tree(tmp_path)

    assert findings == []
    assert count == 2
    (tmp_path / "untracked.txt").write_text(_private_home(), encoding="utf-8")
    findings, _ = privacy_audit.scan_tree(tmp_path)
    assert any(finding.path == "untracked.txt" for finding in findings)


@pytest.mark.skipif(shutil.which("pdfinfo") is None, reason="pdfinfo is unavailable")
def test_pdf_author_metadata_is_audited(tmp_path: Path) -> None:
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    pdf = tmp_path / "paper.pdf"
    figure = Figure()
    figure.subplots().plot([0.0, 1.0], [0.0, 1.0])
    with PdfPages(pdf, metadata={"Author": "Sensitive Person"}) as document:
        document.savefig(figure)

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.rule == "non-allowlisted PDF author" for finding in findings)


def test_generated_provenance_paths_are_portable(tmp_path: Path) -> None:
    internal = ROOT / "data/raw/episode.jsonl"
    external = tmp_path / "episode.jsonl"

    assert label_expert._portable_project_path(internal) == "data/raw/episode.jsonl"
    assert label_expert._portable_project_path(external) == (
        "${PROJECT_ROOT}/external/episode.jsonl"
    )
    provenance = make_tables._provenance(
        tmp_path / "results.parquet", tmp_path / "summary.csv", "abc123"
    )
    assert str(tmp_path) not in provenance
    assert "${PROJECT_ROOT}/external/results.parquet" in provenance
    assert "${PROJECT_ROOT}/external/summary.csv" in provenance


def test_preflight_report_is_privacy_safe(tmp_path: Path) -> None:
    script = ROOT / "scripts/bootstrap/preflight.sh"
    environment = os.environ.copy()
    environment["PROJECT_ROOT"] = str(tmp_path)
    environment["ARENA_WS"] = str(Path.home() / "arena5_ws")
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    report = (tmp_path / "docs/environment_report.txt").read_text(encoding="utf-8")
    assert "project_root=${PROJECT_ROOT}" in report
    assert "arena_ws=${ARENA_WS}" in report
    assert str(Path.home()) not in report
    assert "Processes:" not in report
    assert "PID" not in report
    assert "UUID" not in report
    assert privacy_audit.scan_tree(tmp_path, all_files=True)[0] == []


def test_offline_lock_generation_strips_machine_paths() -> None:
    source = (ROOT / "scripts/bootstrap/create_offline.sh").read_text(encoding="utf-8")

    assert "/^prefix:[[:space:]]/d" in source
    assert "--format=freeze --exclude-editable" in source
    assert "-e packages/ramp_core" in source
    assert "-e packages/ramp_ml" in source
