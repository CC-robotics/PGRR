#!/usr/bin/env python3
"""Validate a 30-slide PPTX, optional PDF export, notes, and privacy."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DeckValidationError(RuntimeError):
    """Raised when a presentation artifact fails release checks."""


def _slide_names(archive: zipfile.ZipFile) -> list[str]:
    names = [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
    return sorted(names, key=lambda value: int(re.search(r"\d+", value).group()))


def _validate_relationships(archive: zipfile.ZipFile) -> None:
    names = set(archive.namelist())
    namespace = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    for rel_name in (name for name in names if name.endswith(".rels")):
        root = ElementTree.fromstring(archive.read(rel_name))
        base = Path(rel_name).parent.parent
        for relationship in root.findall("r:Relationship", namespace):
            if relationship.attrib.get("TargetMode") == "External":
                continue
            target = relationship.attrib.get("Target", "")
            if not target:
                raise DeckValidationError(f"empty relationship target in {rel_name}")
            normalized = (base / target).as_posix()
            parts: list[str] = []
            for part in normalized.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part not in {"", "."}:
                    parts.append(part)
            resolved = "/".join(parts)
            if resolved not in names:
                raise DeckValidationError(f"broken internal relationship: {rel_name} -> {target}")


def _page_count(pdf: Path) -> int:
    executable = shutil.which("pdfinfo")
    if executable is None:
        raise DeckValidationError("pdfinfo is required to validate the presentation PDF")
    completed = subprocess.run(
        [executable, str(pdf)],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", completed.stdout, flags=re.MULTILINE)
    if match is None:
        raise DeckValidationError("pdfinfo did not return a presentation page count")
    return int(match.group(1))


def validate_deck(pptx: Path, notes: Path, pdf: Path | None = None) -> None:
    if not pptx.is_file() or pptx.stat().st_size == 0:
        raise DeckValidationError(f"PPTX is missing or empty: {pptx}")
    locked_test = False
    with zipfile.ZipFile(pptx) as archive:
        slides = _slide_names(archive)
        if len(slides) != 30:
            raise DeckValidationError(f"PPTX must contain exactly 30 slides; found {len(slides)}")
        _validate_relationships(archive)
        xml_text = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )
        structural_forbidden = ("/home/", "file:///")
        found = [token for token in structural_forbidden if token.lower() in xml_text.lower()]
        if found:
            raise DeckValidationError(f"PPTX contains forbidden metadata/text: {found}")
        drawing_namespace = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        visible_text: list[str] = []
        for slide_name in slides:
            slide_root = ElementTree.fromstring(archive.read(slide_name))
            visible_text.extend(
                element.text or "" for element in slide_root.findall(".//a:t", drawing_namespace)
            )
        joined_visible_text = "\n".join(visible_text)
        text_forbidden = ("TBD", "PLACEHOLDER", "NaN")
        text_found = [
            token for token in text_forbidden if token.lower() in joined_visible_text.lower()
        ]
        if text_found:
            raise DeckValidationError(f"PPTX contains forbidden visible placeholders: {text_found}")
        required_visible = (
            "Planning-Guided Failure-Triggered Recovery and Rejoin",
            "Ubuntu 22.04 / ROS2 Humble",
            "Dynamic Window Approach",
            "轨迹生成器 + Critics",
            "DAgger",
            "遥测重建",
            "不是 camera screenshot",
        )
        missing_visible = [token for token in required_visible if token not in joined_visible_text]
        if missing_visible:
            raise DeckValidationError(
                f"PPTX omits required public-name/runtime/evidence labels: {missing_visible}"
            )
        core = archive.read("docProps/core.xml").decode("utf-8", errors="replace")
        creator = re.search(r"<dc:creator>(.*?)</dc:creator>", core)
        if creator and creator.group(1) not in {"", "Charles Chen"}:
            raise DeckValidationError("PPTX creator is not empty or the approved alias")
        media = [name for name in archive.namelist() if name.startswith("ppt/media/")]
        if any(archive.getinfo(name).file_size == 0 for name in media):
            raise DeckValidationError("PPTX contains an empty media relationship")
        runtime_metadata = json.loads(
            (
                PROJECT_ROOT
                / "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json"
            ).read_text(encoding="utf-8")
        )
        runtime_sha = str(runtime_metadata.get("artifacts", {}).get("screenshot_sha256", ""))
        media_hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in media}
        locked_test = "stage=test" in core
        if locked_test and len(media_hashes) < 18:
            raise DeckValidationError(
                "locked-test PPTX must embed at least 18 distinct visual assets"
            )
        if runtime_sha not in media_hashes:
            raise DeckValidationError("PPTX does not embed the SHA-verified Gazebo GUI capture")
        if locked_test:
            required_final_text = (
                "episode ID",
                "pixel SHA256",
                "PGRR 恢复时序",
                "telemetry reconstruction",
                "共同成功条件下的配对效率",
                "共同到达 pair",
            )
            missing_final_text = [
                token for token in required_final_text if token not in joined_visible_text
            ]
            if missing_final_text:
                raise DeckValidationError(
                    f"locked-test PPTX omits final evidence provenance: {missing_final_text}"
                )
            final_rasters = (
                PROJECT_ROOT / "presentation/generated/result_matched_trajectory.png",
                PROJECT_ROOT / "presentation/generated/result_matched_recovery_timeline.png",
            )
            for raster in final_rasters:
                if not raster.is_file() or hashlib.sha256(raster.read_bytes()).hexdigest() not in (
                    media_hashes
                ):
                    raise DeckValidationError(
                        f"locked-test PPTX does not embed verified matched media: {raster.name}"
                    )

    if not notes.is_file():
        raise DeckValidationError(f"speaker notes are missing: {notes}")
    notes_text = notes.read_text(encoding="utf-8")
    headings = re.findall(r"^##\s+\d{2}\.\s+", notes_text, flags=re.MULTILINE)
    if len(headings) != 30:
        raise DeckValidationError(
            f"speaker notes must contain 30 slide sections; found {len(headings)}"
        )
    if "/home/" in notes_text or "file:///" in notes_text:
        raise DeckValidationError("speaker notes leak a local path")
    required_sources = (
        "https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html",
        "https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md",
        "https://doi.org/10.1109/100.580977",
        "https://proceedings.mlr.press/v15/ross11a.html",
    )
    missing_sources = [source for source in required_sources if source not in notes_text]
    if missing_sources:
        raise DeckValidationError(
            f"speaker notes omit authoritative DWB/DAgger sources: {missing_sources}"
        )
    if locked_test and "如果还是 pending" in notes_text:
        raise DeckValidationError("locked-test speaker notes still contain pending-stage guidance")

    if pdf is not None:
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise DeckValidationError(f"presentation PDF is missing or empty: {pdf}")
        if _page_count(pdf) != 30:
            raise DeckValidationError("presentation PDF must contain exactly 30 pages")
        fonts_tool = shutil.which("pdffonts")
        if fonts_tool:
            completed = subprocess.run(
                [fonts_tool, str(pdf)],
                check=True,
                capture_output=True,
                text=True,
            )
            if "Type 3" in completed.stdout or "Type3" in completed.stdout:
                raise DeckValidationError("presentation PDF contains a Type 3 font")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pptx", type=Path, default=PROJECT_ROOT / "presentation/PGRR_report_zh.pptx"
    )
    parser.add_argument(
        "--notes", type=Path, default=PROJECT_ROOT / "presentation/speaker_notes_zh.md"
    )
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()
    try:
        validate_deck(args.pptx, args.notes, args.pdf)
    except (
        DeckValidationError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    suffix = " and 30-page PDF" if args.pdf else ""
    print(f"Presentation PASS: 30-slide PPTX{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
