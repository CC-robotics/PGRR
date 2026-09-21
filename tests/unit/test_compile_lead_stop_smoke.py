from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "student" / "compile_lead_stop_smoke.py"


def test_compile_lead_stop_is_train_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "packages/ramp_core"))
    spec = importlib.util.spec_from_file_location("compile_lead_stop_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.compile_smoke(
        ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml", tmp_path
    )
    assert report["split"] == "train"
    scenario = json.loads(
        (
            tmp_path
            / "generated"
            / "arena"
            / "map_empty"
            / "lead_pedestrian_sudden_stop_low_train_r00_s91500.json"
        ).read_text(encoding="utf-8")
    )
    assert scenario["ramp_metadata"]["seed"] == 91500
    assert scenario["obstacles"]["dynamic"][0]["cyclic_goals"] is False


def test_compile_lead_stop_validation_is_non_test_and_has_distinct_seed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "packages/ramp_core"))
    spec = importlib.util.spec_from_file_location("compile_lead_stop_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.compile_smoke(
        ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml",
        tmp_path,
        split="validation",
    )
    assert report["split"] == "validation"
    assert report["held_out_test_materialized"] is False
    scenario = json.loads(Path(report["json"]).read_text(encoding="utf-8"))
    assert scenario["ramp_metadata"]["seed"] == 93500
    assert scenario["ramp_metadata"]["split"] == "validation"
    assert "test" not in scenario["ramp_metadata"]["scenario_id"]
