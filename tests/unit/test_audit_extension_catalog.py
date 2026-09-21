from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "student" / "audit_extension_catalog.py"
    spec = importlib.util.spec_from_file_location("audit_extension_catalog", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_extension_catalog_passes_teacher_protocol_audit() -> None:
    report = _module().audit(CONFIG)

    assert report["audit_status"] == "PASS"
    assert report["planned_conditions_by_split"] == {"train": 36, "validation": 18}
    assert report["planned_condition_count"] == 54
    assert report["held_out_test_materialized"] is False


def test_audit_rejects_enabled_test_materialization(tmp_path: Path) -> None:
    module = _module()
    unsafe = tmp_path / "unsafe.yaml"
    unsafe.write_text(CONFIG.read_text(encoding="utf-8").replace("enabled: false", "enabled: true"))

    with pytest.raises(ValueError, match="held-out test"):
        module.audit(unsafe)
