#!/usr/bin/env python3
"""Materialize deterministic training variants for each core failure family."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ("head_on_corridor", "doorway_bottleneck", "crossing_flow")


def _scenario_compiler() -> ModuleType:
    path = ROOT / "scripts" / "data" / "compile_scenarios.py"
    spec = importlib.util.spec_from_file_location("ramp_compile_scenarios", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scenario compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialize(base: dict[str, Any], family: str, run_seed: int) -> dict[str, Any]:
    scenario = copy.deepcopy(base)
    rng = np.random.default_rng(run_seed)
    scenario_id = f"{family}_high_mining_seed{run_seed:02d}"
    metadata = scenario["ramp_metadata"]
    metadata.update(
        {
            "scenario_id": scenario_id,
            "split": "train",
            "seed": run_seed,
            "source_scenario_id": base["ramp_metadata"]["scenario_id"],
            "variant_rule": "pedestrian route translation <=0.12 m and speed scale <=8%",
            "human_behavior_model": "deterministic cyclic-waypoint kinematic proxy",
        }
    )
    for actor in scenario["obstacles"]["dynamic"]:
        dx, dy = rng.uniform(-0.12, 0.12, size=2)
        for waypoint in actor["waypoints"]:
            waypoint[0] = round(float(waypoint[0]) + float(dx), 4)
            waypoint[1] = round(float(waypoint[1]) + float(dy), 4)
        actor["pos"] = list(actor["waypoints"][0])
        actor["max_vel"] = round(float(actor["max_vel"]) * float(rng.uniform(0.92, 1.08)), 4)
    return scenario


def materialize(
    output_root: Path,
    seed_count: int,
    manifest_path: Path | None = None,
    *,
    seed_start: int = 0,
    preview_root: Path | None = None,
) -> dict[str, Any]:
    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    if seed_start < 0:
        raise ValueError("seed_start must be non-negative")
    output_root.mkdir(parents=True, exist_ok=True)
    if preview_root is None:
        preview_root = ROOT / "scenarios" / "previews" / "mining"
    preview_root.mkdir(parents=True, exist_ok=True)
    catalog = yaml.safe_load(
        (ROOT / "configs" / "experiments" / "scenario_catalog.yaml").read_text(encoding="utf-8")
    )
    bounds = [float(value) for value in catalog["map"]["bounds_m"]]
    resolution = float(catalog["map"]["preview_resolution_m"])
    compiler = _scenario_compiler()
    records: list[dict[str, Any]] = []
    sources = {
        "head_on_corridor": "head_on_corridor_high_train_s01020.json",
        "doorway_bottleneck": "doorway_bottleneck_high_train_s01120.json",
        "crossing_flow": "crossing_flow_high_train_s01220.json",
    }
    for family in FAMILIES:
        source = ROOT / "scenarios" / "generated" / "arena" / "map_empty" / sources[family]
        base = json.loads(source.read_text(encoding="utf-8"))
        for run_seed in range(seed_start, seed_start + seed_count):
            scenario = _materialize(base, family, run_seed)
            scenario_id = str(scenario["ramp_metadata"]["scenario_id"])
            destination = output_root / f"{scenario_id}.json"
            content = json.dumps(scenario, indent=2, sort_keys=True) + "\n"
            destination.write_text(content, encoding="utf-8")
            preview = preview_root / f"{scenario_id}.png"
            compiler._validate_scenario(scenario, bounds)
            compiler._render_preview(scenario, bounds, resolution, preview)
            records.append(
                {
                    "scenario_id": scenario_id,
                    "family": family,
                    "density": "high",
                    "split": "train",
                    "seed": run_seed,
                    "path": str(
                        destination.relative_to(ROOT)
                        if destination.is_relative_to(ROOT)
                        else destination
                    ),
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "preview": str(
                        preview.relative_to(ROOT) if preview.is_relative_to(ROOT) else preview
                    ),
                    "timeout_s": 120,
                }
            )
    manifest = {
        "schema_version": 1,
        "purpose": "Gate 1 classical-planner failure mining; never final test",
        "seed_start": seed_start,
        "seed_count_per_family": seed_count,
        "episodes": records,
    }
    if manifest_path is None:
        manifest_path = ROOT / "scenarios" / "manifests" / "failure_mining.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    manifest_display = (
        manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path
    )
    return {"manifest": str(manifest_display), "episode_count": len(records)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "scenarios" / "generated" / "mining",
    )
    parser.add_argument("--seed-count", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=0)
    args = parser.parse_args()
    print(
        json.dumps(
            materialize(args.output_root.resolve(), args.seed_count, seed_start=args.seed_start),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
