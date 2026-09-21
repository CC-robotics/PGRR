from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "student" / "compile_extension_train_validation.py"
    spec = importlib.util.spec_from_file_location("compile_extension_train_validation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builds_each_approved_family_as_one_shot_train_validation_payload() -> None:
    module = _module()
    config = module.yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    conditions = module._split_plan().planned_conditions(config)

    for family in ("diagonal_cut_in_corridor", "occluded_side_emergence"):
        condition = next(item for item in conditions if item["family"] == family)
        payload = module.build_scenario(condition, config)
        metadata = payload["ramp_metadata"]
        assert metadata["benchmark_id"] == "pgrr_extension_v1"
        assert metadata["split"] in {"train", "validation"}
        assert metadata["map_id"] == "map_empty"
        assert metadata["replicate"] == condition["repeat_index"]
        assert metadata["prototype_status"] == "smoke_only_not_a_frozen_experiment_protocol"
        assert payload["obstacles"]["dynamic"]
        assert all(actor["cyclic_goals"] is False for actor in payload["obstacles"]["dynamic"])


def test_smoke_compile_never_materializes_test(tmp_path: Path) -> None:
    report = _module().compile_smoke(CONFIG, tmp_path, limit=2)

    assert report["compiled_count"] == 2
    assert report["held_out_test_materialized"] is False
    assert {record["split"] for record in report["records"]} == {"train"}
    assert (tmp_path / "smoke_manifest_all_families_02.json").is_file()


def test_smoke_compile_can_select_one_validation_condition(tmp_path: Path) -> None:
    report = _module().compile_smoke(CONFIG, tmp_path, limit=1, split="validation")

    assert report["compiled_count"] == 1
    assert report["records"][0]["split"] == "validation"
    assert report["held_out_test_materialized"] is False
    assert (tmp_path / "smoke_manifest_all_families_validation_01.json").is_file()
