#!/usr/bin/env python3
"""Validate and summarize the non-test PGRR extension seed plan.

This planning utility deliberately emits only train and validation conditions.
It does not compile simulator JSON, start ROS, train a model, or materialize a
held-out test set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"
PLANNED_SPLITS = ("train", "validation")


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def load_plan(config_path: Path) -> dict[str, Any]:
    """Load and validate the teacher-approved extension planning envelope."""
    config = _require_mapping(yaml.safe_load(config_path.read_text(encoding="utf-8")), "config")
    if config.get("benchmark_id") != "pgrr_extension_v1":
        raise ValueError("benchmark_id must be pgrr_extension_v1")
    if config.get("status") != "planning_train_validation_only":
        raise ValueError("status must keep this catalog train/validation only")
    families = config.get("families")
    densities = _require_mapping(config.get("densities"), "densities")
    splits = _require_mapping(config.get("splits"), "splits")
    reserved_test = _require_mapping(config.get("reserved_held_out_test"), "reserved_held_out_test")
    if not isinstance(families, list) or not families:
        raise ValueError("families must be a non-empty list")
    if reserved_test.get("enabled") is not False:
        raise ValueError("held-out test materialization is intentionally disabled")
    if set(splits) != set(PLANNED_SPLITS):
        raise ValueError("only train and validation may appear in executable splits")
    family_indices = [item.get("family_index") for item in families if isinstance(item, dict)]
    if len(family_indices) != len(families) or len(set(family_indices)) != len(family_indices):
        raise ValueError("every family needs a unique family_index")
    if any(not isinstance(index, int) or index < 0 for index in family_indices):
        raise ValueError("family_index values must be non-negative integers")
    has_invalid_density = any(
        not isinstance(count, int) or count < 1 for count in densities.values()
    )
    if not densities or has_invalid_density:
        raise ValueError("densities must map names to positive integer pedestrian counts")
    return config


def planned_conditions(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic train/validation conditions, never test conditions."""
    conditions: list[dict[str, Any]] = []
    densities = list(_require_mapping(config["densities"], "densities").items())
    for split in PLANNED_SPLITS:
        split_config = _require_mapping(config["splits"][split], f"splits.{split}")
        seed_base = split_config.get("seed_base")
        repeats = split_config.get("repeats_per_family_density")
        if not isinstance(seed_base, int) or not isinstance(repeats, int) or repeats < 1:
            raise ValueError(f"splits.{split} needs integer seed_base and positive repeats")
        for family in config["families"]:
            family_id = family.get("id")
            family_index = family.get("family_index")
            if not isinstance(family_id, str) or not family_id:
                raise ValueError("each family needs a non-empty id")
            for density_index, (density, pedestrian_count) in enumerate(densities):
                for repeat_index in range(repeats):
                    seed = seed_base + 100 * family_index + 10 * density_index + repeat_index
                    conditions.append(
                        {
                            "condition_id": f"{family_id}_{density}_{split}_r{repeat_index:02d}",
                            "family": family_id,
                            "family_index": family_index,
                            "density": density,
                            "pedestrian_count": pedestrian_count,
                            "split": split,
                            "repeat_index": repeat_index,
                            "seed": seed,
                        }
                    )
    return conditions


def validate_conditions(conditions: list[dict[str, Any]]) -> dict[str, int]:
    """Fail if a planned condition or seed can silently overlap across splits."""
    identifiers = [str(item["condition_id"]) for item in conditions]
    seed_keys = [
        (str(item["family"]), str(item["density"]), int(item["seed"]))
        for item in conditions
    ]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate condition_id")
    if len(seed_keys) != len(set(seed_keys)):
        raise ValueError("a family/density/seed combination appears more than once")
    counts = {split: sum(item["split"] == split for item in conditions) for split in PLANNED_SPLITS}
    if not all(counts.values()):
        raise ValueError("both train and validation must contain conditions")
    return counts


def summarize(config: dict[str, Any]) -> dict[str, Any]:
    conditions = planned_conditions(config)
    counts = validate_conditions(conditions)
    test = _require_mapping(config["reserved_held_out_test"], "reserved_held_out_test")
    return {
        "benchmark_id": config["benchmark_id"],
        "status": config["status"],
        "materialized_splits": list(PLANNED_SPLITS),
        "counts_by_split": counts,
        "planned_condition_count": len(conditions),
        "reserved_test": {
            "materialized": False,
            "seed_base": test["seed_base"],
            "repeats_per_family_density": test["repeats_per_family_density"],
        },
        "conditions": conditions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON plan output; no simulator files are created",
    )
    args = parser.parse_args()
    report = summarize(load_plan(args.config.resolve()))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
