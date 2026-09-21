from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "student" / "compile_narrow_corridor_head_on_smoke.py"


def _module():
    spec = importlib.util.spec_from_file_location("compile_head_on_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compile_narrow_corridor_head_on_is_train_only(tmp_path: Path) -> None:
    module = _module()
    report = module.compile_smoke(
        ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml", tmp_path
    )
    assert report["split"] == "train"
    assert report["held_out_test_materialized"] is False
    scenario_path = (
        tmp_path
        / "generated"
        / "arena"
        / "map_empty"
        / "narrow_corridor_head_on_deadlock_low_train_r00_s91300.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["seed"] == 91300
    assert len(scenario["obstacles"]["dynamic"]) == 1
    assert scenario["obstacles"]["dynamic"][0]["cyclic_goals"] is False


def test_compile_narrow_corridor_head_on_validation_is_separate(tmp_path: Path) -> None:
    module = _module()
    report = module.compile_smoke(
        ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml",
        tmp_path,
        split="validation",
    )

    assert report["split"] == "validation"
    assert report["held_out_test_materialized"] is False
    scenario_path = (
        tmp_path
        / "generated"
        / "arena"
        / "map_empty"
        / "narrow_corridor_head_on_deadlock_low_validation_r00_s93300.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["seed"] == 93300
    assert scenario["ramp_metadata"]["split"] == "validation"
