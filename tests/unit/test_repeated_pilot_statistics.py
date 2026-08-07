from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import pytest


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts/evaluate/summarize_repeated_pilot.py"
    spec = spec_from_file_location("summarize_repeated_pilot", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_binomial_interval_handles_boundary_counts() -> None:
    interval = _module().exact_binomial_interval(0, 5)
    assert interval[0] == 0.0
    assert interval[1] == pytest.approx(0.521824, abs=1.0e-5)
    interval = _module().exact_binomial_interval(5, 5)
    assert interval[0] == pytest.approx(0.478176, abs=1.0e-5)
    assert interval[1] == 1.0
