from __future__ import annotations

import copy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import pytest


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts/data/generate_validation_variants.py"
    spec = spec_from_file_location("generate_validation_variants", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scenario(split: str = "validation") -> dict[str, object]:
    return {
        "ramp_metadata": {
            "split": split,
            "family": "crossing_flow",
            "density": "low",
            "scenario_id": "crossing_flow_low_validation_s02200",
            "human_speed_range_mps": [0.45, 0.75],
        },
        "obstacles": {"dynamic": [{"max_vel": 0.5}, {"max_vel": 0.6}]},
    }


def test_validation_variant_is_seeded_and_does_not_mutate_source() -> None:
    source = _scenario()
    original = copy.deepcopy(source)
    first = _module().generate_validation_variant(source, 2201)
    second = _module().generate_validation_variant(source, 2201)
    assert first == second
    assert source == original
    assert first["ramp_metadata"]["scenario_id"] == "crossing_flow_low_validation_s02201"
    assert first["ramp_metadata"]["variant_source"] == original["ramp_metadata"]["scenario_id"]
    assert all(0.45 <= item["max_vel"] <= 0.75 for item in first["obstacles"]["dynamic"])


def test_validation_variant_rejects_training_source() -> None:
    with pytest.raises(ValueError, match="validation source"):
        _module().generate_validation_variant(_scenario("train"), 2201)
