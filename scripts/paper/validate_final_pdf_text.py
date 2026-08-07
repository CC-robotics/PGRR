#!/usr/bin/env python3
"""Fail closed when the final paper PDF still contains pending-stage prose."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Final


class FinalPdfTextError(RuntimeError):
    """Raised when the conference-paper PDF is not a final evidence-bound build."""


REQUIRED_FINAL_MARKERS: Final[dict[str, str]] = {
    "moderate-v6 benchmark identity": "moderate-v6",
    "v6 held-out outcome caption": "Held-out three-density Gazebo outcomes",
    "real Gazebo pixel-capture caption": "Pixel capture from the mapped Gazebo GUI",
    "matched telemetry caption": (
        "Matched measured execution generated from final Parquet and raw episode streams"
    ),
    "matched telemetry representation disclosure": (
        "telemetry reconstructions, not simulator or onboard camera screenshots"
    ),
}

FORBIDDEN_PENDING_MARKERS: Final[tuple[str, ...]] = (
    "Artifact-Gated Outcome Status",
    "no held-out numerical claim",
    "contains no v6 test number",
    "test split remained sealed",
)


def _normalise_pdf_text(text: str) -> str:
    normalised = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    return re.sub(r"\s+", " ", normalised).strip()


def validate_final_text(text: str) -> None:
    """Require final-result and real-evidence captions and reject pending prose."""

    normalised = _normalise_pdf_text(text)
    folded = normalised.casefold()
    forbidden = [marker for marker in FORBIDDEN_PENDING_MARKERS if marker.casefold() in folded]
    if forbidden:
        raise FinalPdfTextError(
            "conference paper still contains pending-stage prose: " + ", ".join(forbidden)
        )
    missing = [
        label for label, marker in REQUIRED_FINAL_MARKERS.items() if marker.casefold() not in folded
    ]
    if missing:
        raise FinalPdfTextError(
            "conference paper omits required final evidence text: " + ", ".join(missing)
        )


def extract_pdf_text(path: Path) -> str:
    """Extract UTF-8 text using the release-declared Poppler tooling."""

    executable = shutil.which("pdftotext")
    if executable is None:
        raise FinalPdfTextError("pdftotext is required to validate the final conference paper")
    try:
        completed = subprocess.run(
            [executable, str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FinalPdfTextError(f"cannot extract text from conference paper: {path}") from error
    return completed.stdout


def validate_final_pdf(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FinalPdfTextError(f"missing final conference paper: {path}")
    validate_final_text(extract_pdf_text(path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    validate_final_pdf(args.paper)
    print(f"Final paper text PASS: {args.paper}")


if __name__ == "__main__":
    try:
        main()
    except FinalPdfTextError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
