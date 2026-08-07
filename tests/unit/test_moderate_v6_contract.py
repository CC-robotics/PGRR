"""Freeze the moderate-v6 revision and all deterministic compiled conditions."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
V5_CONFIG = ROOT / "configs/experiments/scenario_catalog_moderate_v5.yaml"
V6_CONFIG = ROOT / "configs/experiments/scenario_catalog_moderate_v6.yaml"
COMPILER = ROOT / "scripts/data/compile_moderate_benchmark.py"
EXPECTED_COUNTS = {"train": 72, "validation": 72, "test": 120}
EXPECTED_SEED_BASES = {"train": 76000, "validation": 77000, "test": 87000}
EXPECTED_FILE_SHA256 = {
    "catalog": "efaf573294d2484a616f039e9e2e4380ae89e60411a2ad12b04c36072cfe404f",
    "validation": "f5847bcea4999bc5537f0e648cf76020fcf148e839b9908cc38eaffe21844d0f",
    "test": "3f70dd3472c0447d6a5695051f0b16d7eecf166133b604a7011cdf7fc45b04f6",
}


def _compiler() -> Any:
    spec = importlib.util.spec_from_file_location("pgrr_v6_contract_compiler", COMPILER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path, split: str) -> dict[str, Any]:
    payload = yaml.safe_load((root / "splits" / f"moderate_v6_{split}.yaml").read_text())
    assert isinstance(payload, dict)
    return payload


def test_v6_changes_only_crossing_phase_plus_identity_and_fresh_seed_blocks() -> None:
    v5 = yaml.safe_load(V5_CONFIG.read_text(encoding="utf-8"))
    v6 = yaml.safe_load(V6_CONFIG.read_text(encoding="utf-8"))

    assert v6["benchmark_id"] == "moderate_social_navigation_v6"
    assert v6["families"][2]["id"] == "crossing_flow"
    assert v5["families"][2]["speed_range_mps"] == [0.35, 0.55]
    assert v6["families"][2]["speed_range_mps"] == [0.18, 0.28]
    assert {name: row["seed_base"] for name, row in v6["splits"].items()} == (EXPECTED_SEED_BASES)
    v5_seed_blocks = {int(row["seed_base"]) // 1000 for row in v5["splits"].values()}
    v6_seed_blocks = {int(row["seed_base"]) // 1000 for row in v6["splits"].values()}
    assert v5_seed_blocks.isdisjoint(v6_seed_blocks)

    normalized = copy.deepcopy(v6)
    normalized["benchmark_id"] = v5["benchmark_id"]
    normalized["output"] = copy.deepcopy(v5["output"])
    for split in normalized["splits"]:
        normalized["splits"][split]["seed_base"] = v5["splits"][split]["seed_base"]
    normalized["families"][2]["speed_range_mps"] = copy.deepcopy(
        v5["families"][2]["speed_range_mps"]
    )
    assert normalized == v5


def test_v6_full_recompile_matches_all_264_frozen_hashes_and_split_isolation(
    tmp_path: Path,
) -> None:
    compiler = _compiler()
    summary = compiler.compile_benchmark(V6_CONFIG, tmp_path, render_previews=False)
    committed_summary = json.loads(
        (ROOT / "scenarios/manifests/scenario_catalog_moderate_v6.json").read_text(encoding="utf-8")
    )
    assert summary["benchmark_id"] == "moderate_social_navigation_v6"
    assert summary["counts_by_split"] == EXPECTED_COUNTS
    assert summary["scenario_count"] == 264
    assert summary["scenario_ids_sha256"] == committed_summary["scenario_ids_sha256"]

    split_values: dict[str, dict[str, set[object]]] = {}
    all_hashes: set[object] = set()
    for split, expected_count in EXPECTED_COUNTS.items():
        generated = _manifest(tmp_path, split)
        committed = _manifest(ROOT / "scenarios", split)
        assert generated["benchmark_id"] == "moderate_social_navigation_v6"
        assert generated["split"] == split
        generated_rows = generated["scenarios"]
        committed_rows = committed["scenarios"]
        assert len(generated_rows) == len(committed_rows) == expected_count
        assert [(row["scenario_id"], row["seed"], row["sha256"]) for row in generated_rows] == [
            (row["scenario_id"], row["seed"], row["sha256"]) for row in committed_rows
        ]

        identifiers = {row["scenario_id"] for row in generated_rows}
        seeds = {row["seed"] for row in generated_rows}
        hashes = {row["sha256"] for row in generated_rows}
        assert len(identifiers) == len(seeds) == len(hashes) == expected_count
        assert all(
            EXPECTED_SEED_BASES[split] <= int(seed) < EXPECTED_SEED_BASES[split] + 1000
            for seed in seeds
        )
        for row in generated_rows:
            scenario_path = tmp_path / "generated" / row["path"]
            assert _sha256(scenario_path) == row["sha256"]
        split_values[split] = {"ids": identifiers, "seeds": seeds, "hashes": hashes}
        all_hashes.update(hashes)

    assert len(all_hashes) == 264
    for left, right in combinations(EXPECTED_COUNTS, 2):
        for key in ("ids", "seeds", "hashes"):
            assert split_values[left][key].isdisjoint(split_values[right][key])

    assert _sha256(V6_CONFIG) == EXPECTED_FILE_SHA256["catalog"]
    assert (
        _sha256(ROOT / "scenarios/splits/moderate_v6_validation.yaml")
        == (EXPECTED_FILE_SHA256["validation"])
    )
    assert (
        _sha256(ROOT / "scenarios/splits/moderate_v6_test.yaml") == (EXPECTED_FILE_SHA256["test"])
    )
