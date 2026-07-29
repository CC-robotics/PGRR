from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "data" / "materialize_failure_mining.py"
    spec = importlib.util.spec_from_file_location("materialize_failure_mining", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_mining_manifest_has_ten_unique_seeds_per_family(tmp_path: Path) -> None:
    module = _module()
    summary = module.materialize(
        tmp_path / "variants",
        10,
        tmp_path / "failure_mining.yaml",
        preview_root=tmp_path / "previews",
    )
    assert summary["episode_count"] == 30
    manifest = yaml.safe_load(Path(summary["manifest"]).read_text())
    records = manifest["episodes"]
    assert len({record["scenario_id"] for record in records}) == 30
    for family in ("head_on_corridor", "doorway_bottleneck", "crossing_flow"):
        selected = [record for record in records if record["family"] == family]
        assert {record["seed"] for record in selected} == set(range(10))
        for record in selected:
            scenario = json.loads(Path(record["path"]).read_text())
            assert scenario["ramp_metadata"]["split"] == "train"
            assert Path(record["preview"]).is_file()
