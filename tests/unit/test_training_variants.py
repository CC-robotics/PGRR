from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


def _module() -> Any:
    path = Path(__file__).resolve().parents[2] / "scripts/data/generate_speed_variants.py"
    spec = spec_from_file_location("generate_speed_variants", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_speed_variant_changes_only_train_seed_speed_and_provenance() -> None:
    source: dict[str, object] = {
        "ramp_metadata": {
            "scenario_id": "crossing_flow_high_train_s01220",
            "family": "crossing_flow",
            "density": "high",
            "split": "train",
            "seed": 1220,
            "human_speed_range_mps": [0.45, 0.75],
        },
        "obstacles": {"dynamic": [{"max_vel": 0.5}, {"max_vel": 0.6}]},
        "robots": [{"start": [5.0, 12.0, 0.0], "goal": [26.0, 12.0, 0.0]}],
    }
    variant = _module().generate_variant(source, 1260)
    metadata = variant["ramp_metadata"]
    assert metadata["split"] == "train"
    assert metadata["seed"] == 1260
    assert metadata["variant_source"] == "crossing_flow_high_train_s01220"
    assert source["ramp_metadata"]["seed"] == 1220
