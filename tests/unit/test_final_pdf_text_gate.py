from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paper/validate_final_pdf_text.py"
SPEC = importlib.util.spec_from_file_location("validate_final_pdf_text_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _valid_text() -> str:
    return "\n".join(MODULE.REQUIRED_FINAL_MARKERS.values())


def test_final_pdf_text_gate_accepts_all_required_evidence_captions() -> None:
    MODULE.validate_final_text(_valid_text())


@pytest.mark.parametrize("marker", MODULE.FORBIDDEN_PENDING_MARKERS)
def test_final_pdf_text_gate_rejects_pending_prose(marker: str) -> None:
    with pytest.raises(MODULE.FinalPdfTextError, match="pending-stage prose"):
        MODULE.validate_final_text(f"{_valid_text()}\n{marker}")


@pytest.mark.parametrize("missing_label", MODULE.REQUIRED_FINAL_MARKERS)
def test_final_pdf_text_gate_requires_each_final_caption(missing_label: str) -> None:
    text = "\n".join(
        marker for label, marker in MODULE.REQUIRED_FINAL_MARKERS.items() if label != missing_label
    )
    with pytest.raises(MODULE.FinalPdfTextError, match=missing_label):
        MODULE.validate_final_text(text)


def test_final_pdf_text_gate_requires_pdftotext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paper = tmp_path / "main.pdf"
    paper.write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(MODULE.shutil, "which", lambda _name: None)
    with pytest.raises(MODULE.FinalPdfTextError, match="pdftotext is required"):
        MODULE.validate_final_pdf(paper)
