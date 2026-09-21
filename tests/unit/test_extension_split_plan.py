from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "student" / "validate_extension_split.py"
    spec = importlib.util.spec_from_file_location("validate_extension_split", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extension_plan_materializes_only_train_and_validation() -> None:
    module = _module()
    config = module.load_plan(CONFIG)
    report = module.summarize(config)

    assert report["benchmark_id"] == "pgrr_extension_v1"
    assert report["materialized_splits"] == ["train", "validation"]
    assert report["counts_by_split"] == {"train": 36, "validation": 18}
    assert report["planned_condition_count"] == 54
    assert report["reserved_test"]["materialized"] is False
    assert {item["split"] for item in report["conditions"]} == {"train", "validation"}


def test_extension_plan_uses_teacher_seed_formula() -> None:
    module = _module()
    config = module.load_plan(CONFIG)
    conditions = module.planned_conditions(config)
    first_train = next(
        item
        for item in conditions
        if item["condition_id"] == "diagonal_cut_in_corridor_low_train_r00"
    )
    first_validation_family_two = next(
        item
        for item in conditions
        if item["condition_id"] == "occluded_side_emergence_medium_validation_r02"
    )

    assert first_train["seed"] == 91000
    assert first_validation_family_two["seed"] == 93000 + 100 + 10 + 2
