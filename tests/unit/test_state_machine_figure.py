from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "paper" / "make_state_machine_figure.py"
SPEC = importlib.util.spec_from_file_location("pgrr_state_machine_figure", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

sys.path.insert(0, str(ROOT / "packages" / "ramp_core"))
from ramp_core.state_machine import RecoveryState  # noqa: E402


def test_figure_inventory_matches_core_state_machine() -> None:
    runtime_states = {state.value for state in RecoveryState}
    assert set(MODULE.FIGURE_STATES) == runtime_states
    assert set(MODULE.STATE_LAYOUT) == runtime_states
    assert MODULE.SAFETY_PREEMPT_SOURCES == {
        "NORMAL",
        "PENDING_RECOVERY",
        "RECOVERY",
        "REJOIN",
    }
    assert MODULE.SAFETY_CLEAR_TARGETS == MODULE.SAFETY_PREEMPT_SOURCES
    assert MODULE.GLOBAL_TERMINAL_TARGETS == {"FAILED", "SUCCEEDED"}
    assert MODULE.GLOBAL_FAILURE_GUARDS == {
        "unrecoverable_failure",
        "recovery_sequence_timeout",
    }


def test_figure_inventory_covers_every_current_state_changing_branch() -> None:
    assert MODULE.NOMINAL_TRANSITIONS == {
        ("NORMAL", "PENDING_RECOVERY"),
        ("NORMAL", "RECOVERY"),
        ("NORMAL", "FAILED"),
        ("PENDING_RECOVERY", "NORMAL"),
        ("PENDING_RECOVERY", "RECOVERY"),
        ("PENDING_RECOVERY", "FAILED"),
        ("RECOVERY", "REJOIN"),
        ("REJOIN", "RECOVERY"),
        ("REJOIN", "NORMAL"),
    }
    assert len(MODULE.FUNCTIONAL_COLORS) == 3


def test_figure_writes_vector_pdf_and_high_resolution_png(tmp_path: Path) -> None:
    pdf_path, png_path = MODULE.generate(tmp_path)
    pdf = pdf_path.read_bytes()
    assert pdf.startswith(b"%PDF")
    # A diagram made entirely from vector patches/text must not contain a
    # raster image XObject in its PDF representation.
    assert b"/Subtype /Image" not in pdf
    assert pdf_path.stat().st_size > 10_000

    with Image.open(png_path) as image:
        assert image.format == "PNG"
        assert image.width >= 2_000
        assert image.height >= 1_000
        assert image.getpixel((0, 0))[:3] == (255, 255, 255)
