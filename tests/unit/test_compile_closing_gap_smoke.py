from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "student" / "compile_closing_gap_smoke.py"


def _module():
    spec = importlib.util.spec_from_file_location("compile_closing_gap_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compile_closing_gap_is_train_only(tmp_path: Path) -> None:
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
        / "closing_gap_multi_pedestrian_medium_train_r00_s91410.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["seed"] == 91410
    assert len(scenario["obstacles"]["dynamic"]) == 2
