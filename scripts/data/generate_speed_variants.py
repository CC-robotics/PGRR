#!/usr/bin/env python3
"""Generate train-only deterministic pedestrian-speed scenario variants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def generate_variant(source: dict[str, object], seed: int) -> dict[str, object]:
    payload = json.loads(json.dumps(source))
    metadata = payload["ramp_metadata"]
    if metadata["split"] != "train":
        raise ValueError("speed variants may only be generated from the train split")
    low, high = (float(value) for value in metadata["human_speed_range_mps"])
    humans = payload["obstacles"]["dynamic"]
    rng = np.random.default_rng(seed)
    for human in humans:
        human["max_vel"] = round(float(rng.uniform(low, high)), 4)
    family = str(metadata["family"])
    density = str(metadata["density"])
    scenario_id = f"{family}_{density}_train_s{seed:05d}"
    metadata["scenario_id"] = scenario_id
    metadata["seed"] = seed
    metadata["variant_source"] = str(source["ramp_metadata"]["scenario_id"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "scenarios/generated/arena/map_empty",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "scenarios/manifests/dagger_train_variants.yaml",
    )
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        variant = generate_variant(source, seed)
        scenario_id = str(variant["ramp_metadata"]["scenario_id"])
        target = args.output_directory / f"{scenario_id}.json"
        serialized = json.dumps(variant, indent=2, sort_keys=True) + "\n"
        target.write_text(serialized, encoding="utf-8")
        records.append(
            {
                "scenario_id": scenario_id,
                "seed": seed,
                "path": str(target.relative_to(ROOT)),
                "sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            }
        )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split": "train",
                "source": str(args.source),
                "variants": records,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"Generated train variants={len(records)} manifest={args.manifest}")


if __name__ == "__main__":
    main()
