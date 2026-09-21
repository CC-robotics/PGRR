from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "student" / "audit_eight_family_draft.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_eight_family_draft", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eight_family_draft_has_a_safe_non_test_plan() -> None:
    module = _module()
    report = module.audit(
        ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
    )
    assert report["audit_status"] == "PASS"
    assert report["family_count"] == 8
    assert report["conditions_by_split"] == {"train": 144, "validation": 72}
    assert report["planned_condition_count"] == 216
    assert report["held_out_test_materialized"] is False
    assert report["executable"] is False
