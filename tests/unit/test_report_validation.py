from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/report/validate_report.py"
SPEC = importlib.util.spec_from_file_location("validate_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize("pages", [31, 33])
def test_locked_test_report_requires_exactly_32_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pages: int,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF fixture\n")
    data = tmp_path / "report_data.json"
    data.write_text(json.dumps({"stage": "test"}), encoding="utf-8")
    monkeypatch.setattr(MODULE, "_page_count", lambda _path: pages)

    with pytest.raises(MODULE.ReportValidationError, match="exactly 32 pages"):
        MODULE.validate_report(pdf, data)


@pytest.mark.parametrize(("stage", "pages"), [("pending", 20), ("validation", 25)])
def test_non_test_report_page_ranges_remain_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    pages: int,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF fixture\n")
    data = tmp_path / "report_data.json"
    data.write_text(json.dumps({"stage": stage}), encoding="utf-8")
    monkeypatch.setattr(MODULE, "_page_count", lambda _path: pages - 1)

    with pytest.raises(MODULE.ReportValidationError, match="must contain"):
        MODULE.validate_report(pdf, data)
