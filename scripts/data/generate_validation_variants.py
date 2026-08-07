#!/usr/bin/env python3
"""Generate validation-only pedestrian-speed variants and an immutable manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def generate_validation_variant(source: dict[str, Any], seed: int) -> dict[str, Any]:
    """Return a deep-copied validation scenario with seeded actor speeds."""

    payload: dict[str, Any] = json.loads(json.dumps(source))
    metadata = payload["ramp_metadata"]
    if metadata["split"] != "validation":
        raise ValueError("validation variants require a validation source")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    low, high = (float(value) for value in metadata["human_speed_range_mps"])
    rng = np.random.default_rng(seed)
    for human in payload["obstacles"]["dynamic"]:
        human["max_vel"] = round(float(rng.uniform(low, high)), 4)
    family = str(metadata["family"])
    density = str(metadata["density"])
    scenario_id = f"{family}_{density}_validation_s{seed:05d}"
    metadata["scenario_id"] = scenario_id
    metadata["seed"] = seed
    metadata["variant_source"] = str(source["ramp_metadata"]["scenario_id"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "scenarios/generated/arena/map_empty",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "scenarios/manifests/crossing_flow_validation_variants.yaml",
    )
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for source_path in args.sources:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        for seed in args.seeds:
            variant = generate_validation_variant(source, seed)
            scenario_id = str(variant["ramp_metadata"]["scenario_id"])
            target = args.output_directory / f"{scenario_id}.json"
            serialized = json.dumps(variant, indent=2, sort_keys=True) + "\n"
            target.write_text(serialized, encoding="utf-8")
            records.append(
                {
                    "scenario_id": scenario_id,
                    "seed": seed,
                    "source": str(source_path.resolve().relative_to(ROOT)),
                    "path": str(target.relative_to(ROOT)),
                    "sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                }
            )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "split": "validation", "variants": records},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"Generated validation variants={len(records)} manifest={args.manifest}")


if __name__ == "__main__":
    main()
