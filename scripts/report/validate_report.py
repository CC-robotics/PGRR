#!/usr/bin/env python3
"""Validate page count, stage labeling, fonts, privacy, and placeholders."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReportValidationError(RuntimeError):
    """Raised when the generated technical report is not releasable."""


def _run(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _page_count(pdf: Path) -> int:
    executable = shutil.which("pdfinfo")
    if executable is None:
        raise ReportValidationError("pdfinfo is required to validate the technical report")
    output = _run([executable, str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", output, flags=re.MULTILINE)
    if match is None:
        raise ReportValidationError("pdfinfo did not report a page count")
    return int(match.group(1))


def _pdf_text(pdf: Path) -> str:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise ReportValidationError("pdftotext is required for privacy validation")
    return _run([executable, str(pdf), "-"])


def validate_report(pdf: Path, data_path: Path, log_path: Path | None = None) -> int:
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise ReportValidationError(f"technical report PDF is missing or empty: {pdf}")
    if not data_path.is_file():
        raise ReportValidationError(f"report stage data is missing: {data_path}")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    stage = str(data.get("stage"))
    if stage not in {"pending", "validation", "test"}:
        raise ReportValidationError(f"unknown report stage: {stage!r}")
    pages = _page_count(pdf)
    minimum = 20 if stage == "pending" else 25
    if not minimum <= pages <= 35:
        raise ReportValidationError(
            f"stage={stage} report must contain {minimum}--35 pages; found {pages}"
        )

    text = _pdf_text(pdf)
    forbidden = ("/home/", "file:///", "TBD", "PLACEHOLDER", "待填数字")
    found = [token for token in forbidden if token.lower() in text.lower()]
    if found:
        raise ReportValidationError(f"report contains forbidden metadata/text tokens: {found}")
    if "Charles Chen" not in text:
        raise ReportValidationError("report author alias is missing")
    if stage == "pending":
        if "结果尚未锁定" not in text and "结果待锁定" not in text:
            raise ReportValidationError("pending report lacks an explicit pending-stage label")
    elif stage == "validation" and "非最终" not in text:
        raise ReportValidationError(
            "validation report must state that it is not final test evidence"
        )

    pdfinfo = _run([shutil.which("pdfinfo") or "pdfinfo", str(pdf)])
    if "/home/" in pdfinfo or "file:///" in pdfinfo:
        raise ReportValidationError("PDF metadata leaks a local path")
    fonts_tool = shutil.which("pdffonts")
    if fonts_tool:
        fonts = _run([fonts_tool, str(pdf)])
        for line in fonts.splitlines()[2:]:
            fields = line.split()
            if not fields:
                continue
            if "Type 3" in line or "Type3" in line:
                raise ReportValidationError("technical report contains a Type 3 font")
            if len(fields) >= 6 and fields[5].lower() == "no":
                raise ReportValidationError("technical report contains an unembedded font")
    if log_path and log_path.is_file():
        log = log_path.read_text(encoding="utf-8", errors="replace")
        patterns = (
            r"undefined references",
            r"Citation .* undefined",
            r"Reference .* undefined",
            r"Overfull \\hbox",
        )
        if any(re.search(pattern, log, flags=re.IGNORECASE) for pattern in patterns):
            raise ReportValidationError(
                "technical report log contains unresolved or overflow errors"
            )
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf", type=Path, default=PROJECT_ROOT / "report/PGRR_technical_report_zh.pdf"
    )
    parser.add_argument(
        "--data", type=Path, default=PROJECT_ROOT / "report/generated/report_data.json"
    )
    parser.add_argument("--log", type=Path, default=PROJECT_ROOT / "report/technical_report.log")
    args = parser.parse_args()
    try:
        pages = validate_report(args.pdf, args.data, args.log)
    except (ReportValidationError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Technical report PASS: {args.pdf} ({pages} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
