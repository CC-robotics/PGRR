from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_load_draft_and_reject_test_payload() -> None:
    spec = importlib.util.spec_from_file_location(
        "common", ROOT / "scripts/student/eight_family_common.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.load_draft(
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml"
    )
    assert len(config["families"]) == 8
    with pytest.raises(ValueError, match="never materialize test"):
        module.write_smoke(
            config,
            {"ramp_metadata": {"split": "test"}},
            ROOT / "outputs/student",
            "x",
        )
