from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from xml.sax.saxutils import escape

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


def _runtime_home() -> str:
    return str(Path.home())


def _runtime_hostname() -> str:
    return socket.gethostname()


def _write_minimal_pptx(
    path: Path,
    *,
    creator: str = "Charles Chen",
    last_modified_by: str = "Charles Chen",
    slide_text: str = "portable release",
    external_target: str | None = None,
    media: bytes | None = None,
) -> None:
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
 <dc:creator>{escape(creator)}</dc:creator>
 <cp:lastModifiedBy>{escape(last_modified_by)}</cp:lastModifiedBy>
</cp:coreProperties>
"""
    slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:name>{escape(slide_text)}</p:name></p:cSld>
</p:sld>
"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />
"""
    if external_target is not None:
        relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="urn:pgrr:test" Target="{escape(external_target)}"
  TargetMode="External" />
</Relationships>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" />
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", relationships)
        if media is not None:
            archive.writestr("ppt/media/image1.png", media)


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
        f"root={_runtime_home()}/PGRR\nhostname={_runtime_hostname()}\n"
        "maintainer=" + "ramp-local" + "@" + "example.com\n",
        encoding="utf-8",
    )
    (tmp_path / "model.bin").write_bytes(
        b"\x00model metadata\x00" + _runtime_home().encode() + b"/checkpoint\x00"
    )

    findings, count = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert count == 2
    assert {finding.source for finding in findings} >= {"text", "binary-strings"}
    assert any(finding.rule == "non-allowlisted email address" for finding in findings)
    assert privacy_audit.main([str(tmp_path), "--all-files"]) == 1


def test_private_identifier_in_filename_is_rejected(tmp_path: Path) -> None:
    (tmp_path / f"report_{_runtime_hostname()}.txt").write_text(
        "Anonymous Authors\n", encoding="utf-8"
    )

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "path" for finding in findings)


def test_hdf5_attributes_are_audited(tmp_path: Path) -> None:
    dataset = tmp_path / "expert.h5"
    with h5py.File(dataset, "w") as handle:
        handle.attrs["source_jsonl"] = _runtime_home() + "/raw/episode.jsonl"

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "hdf5-attribute" for finding in findings)
    assert any("source_jsonl" in finding.rule for finding in findings)


def test_default_git_surface_includes_untracked_but_not_ignored(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.bin\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Anonymous Authors\n", encoding="utf-8")
    (tmp_path / "ignored.bin").write_text(_runtime_home(), encoding="utf-8")

    findings, count = privacy_audit.scan_tree(tmp_path)

    assert findings == []
    assert count == 2
    (tmp_path / "untracked.txt").write_text(_runtime_home(), encoding="utf-8")
    findings, _ = privacy_audit.scan_tree(tmp_path)
    assert any(finding.path == "untracked.txt" for finding in findings)


@pytest.mark.parametrize(
    "source",
    [
        'marker = "private-" + "machine-" + "marker"\n',
        'marker = ("private-" "machine-" "marker")\n',
    ],
)
def test_concatenated_forbidden_identifier_cannot_evade_scan(source: str) -> None:
    forbidden = "private-machine-marker"

    findings = privacy_audit._scan_text(
        source,
        "module.py",
        "text",
        extra_forbidden=[forbidden],
    )

    assert any(
        finding.rule == "forbidden machine/user identifier assembled from string literals"
        for finding in findings
    )


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "scripts/bootstrap/privacy_audit.py",
        ROOT / "tests/unit/test_privacy_audit.py",
    ],
)
def test_privacy_sources_do_not_reconstruct_runtime_identifiers(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    sensitive = privacy_audit._sensitive_literals(())
    assembled = privacy_audit._concatenated_string_literals(source)

    assert all(literal.casefold() not in source.casefold() for literal in sensitive)
    assert all(
        literal.casefold() not in value.casefold()
        for value, _ in assembled
        for literal in sensitive
    )


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


@pytest.mark.skipif(
    shutil.which("pdfinfo") is None or shutil.which("pdftotext") is None,
    reason="Poppler PDF tools are unavailable",
)
def test_compressed_pdf_body_text_is_audited(tmp_path: Path) -> None:
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    pdf = tmp_path / "paper.pdf"
    figure = Figure()
    figure.text(0.05, 0.5, _runtime_home() + "/private/report-source.tex")
    with PdfPages(pdf, metadata={"Author": "Charles Chen"}) as document:
        document.savefig(figure)

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "pdf-text" for finding in findings)


def test_clean_office_zip_allows_only_approved_alias(tmp_path: Path) -> None:
    presentation = tmp_path / "briefing.pptx"
    _write_minimal_pptx(
        presentation,
        external_target="https://example.org/public-paper",
    )

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert not any(finding.source.startswith("office-") for finding in findings)


def test_office_core_properties_and_compressed_xml_are_audited(tmp_path: Path) -> None:
    presentation = tmp_path / "briefing.pptx"
    _write_minimal_pptx(
        presentation,
        creator="Sensitive Person",
        last_modified_by="Sensitive Editor",
        slide_text=_runtime_home() + "/private/slide-source.png",
    )

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(
        finding.source == "office-core-properties" and "creator" in finding.rule
        for finding in findings
    )
    assert any(
        finding.source == "office-core-properties" and "lastmodifiedby" in finding.rule
        for finding in findings
    )
    assert any(finding.source == "office-xml" for finding in findings)


def test_office_external_relationship_is_decoded_and_audited(tmp_path: Path) -> None:
    presentation = tmp_path / "briefing.pptx"
    encoded_private_target = "file://" + _runtime_home().replace("/", "%2F") + "%2Fnotes.txt"
    _write_minimal_pptx(presentation, external_target=encoded_private_target)

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "office-external-relationship" for finding in findings)


def test_office_embedded_image_metadata_is_audited(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    PngImagePlugin = pytest.importorskip("PIL.PngImagePlugin")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Author", "Sensitive Person")
    metadata.add_text("Source", _runtime_home() + "/private/render.py")
    payload = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(payload, format="PNG", pnginfo=metadata)
    presentation = tmp_path / "briefing.pptx"
    _write_minimal_pptx(presentation, media=payload.getvalue())

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.source == "office-media-metadata" for finding in findings)
    assert any("embedded Office media" in finding.rule for finding in findings)


def test_unreadable_or_incomplete_office_zip_fails_closed(tmp_path: Path) -> None:
    unreadable = tmp_path / "unreadable.pptx"
    unreadable.write_bytes(b"not a ZIP package")
    incomplete = tmp_path / "incomplete.pptx"
    with zipfile.ZipFile(incomplete, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" />',
        )

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(
        finding.path == "unreadable.pptx" and finding.source == "office-archive"
        for finding in findings
    )
    assert any(
        finding.path == "incomplete.pptx" and finding.source == "office-core-properties"
        for finding in findings
    )


def test_windows_home_path_is_rejected() -> None:
    separator = chr(92)
    windows_home = separator.join(("C:", "Users", "Sensitive Person", "slides.pptx"))
    findings = privacy_audit._scan_text(
        f"source={windows_home}",
        "metadata.txt",
        "text",
    )

    assert any(finding.rule == "absolute Windows home-directory path" for finding in findings)


def test_compressed_png_metadata_is_audited(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    PngImagePlugin = pytest.importorskip("PIL.PngImagePlugin")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Author", "Sensitive Person")
    metadata.add_text("Source", _runtime_home() + "/private/render.py")
    image_path = tmp_path / "figure.png"
    Image.new("RGB", (2, 2), "white").save(image_path, pnginfo=metadata)

    findings, _ = privacy_audit.scan_tree(tmp_path, all_files=True)

    assert any(finding.rule == "non-allowlisted image author" for finding in findings)
    assert any(finding.source == "image-metadata" for finding in findings)
    assert any("Source" in finding.rule for finding in findings)


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
    assert "clean_env conda run" in source
    assert "-u PYTHONPATH" in source
    assert "-u ROS_DISTRO" in source
    assert "-e packages/ramp_core" in source
    assert "-e packages/ramp_ml" in source
