#!/usr/bin/env python3
"""Audit the PGRR extension configuration before any scenario compilation.

This is a pure configuration audit.  It does not compile JSON worlds, run ROS,
or materialize a held-out test set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"
EXPECTED_FAMILIES = {
    "diagonal_cut_in_corridor": {
        "cut_side",
        "cut_angle_deg",
        "longitudinal_phase",
        "speed_ratio_to_robot_nominal",
        "lateral_offset_m",
    },
    "occluded_side_emergence": {
        "emergence_side",
        "first_visible_distance_m",
        "gap_location",
        "longitudinal_phase",
        "pedestrian_speed_mps",
    },
}
EXPECTED_DENSITIES = {"low": 1, "medium": 2, "high": 4}
EXPECTED_SPLITS = {
    "train": (91000, 6),
    "validation": (93000, 3),
}
RESERVED_TEST = (97000, 5)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def audit(config_path: Path) -> dict[str, Any]:
    """Return a compact audit record or fail on a protocol inconsistency."""
    text = config_path.read_text(encoding="utf-8")
    config = _mapping(yaml.safe_load(text), "config")
    if config.get("benchmark_id") != "pgrr_extension_v1":
        raise ValueError("benchmark_id must be pgrr_extension_v1")
    if config.get("status") != "planning_train_validation_only":
        raise ValueError("catalog must remain train/validation planning only")
    densities = _mapping(config.get("densities"), "densities")
    if densities != EXPECTED_DENSITIES:
        raise ValueError("densities must be low/medium/high = 1/2/4")
    families = config.get("families")
    if not isinstance(families, list) or len(families) != len(EXPECTED_FAMILIES):
        raise ValueError("catalog must contain exactly the two approved family specifications")
    seen_indices: set[int] = set()
    audited_families: list[str] = []
    for family in families:
        if not isinstance(family, dict):
            raise ValueError("every family must be a mapping")
        family_id = family.get("id")
        if family_id not in EXPECTED_FAMILIES:
            raise ValueError(f"unapproved extension family: {family_id}")
        variables = _mapping(family.get("variables"), f"variables for {family_id}")
        if set(variables) != EXPECTED_FAMILIES[family_id]:
            raise ValueError(f"{family_id} variables must match the approved research-question set")
        index = family.get("family_index")
        if not isinstance(index, int) or index < 0 or index in seen_indices:
            raise ValueError("family_index values must be unique non-negative integers")
        seen_indices.add(index)
        audited_families.append(str(family_id))
    splits = _mapping(config.get("splits"), "splits")
    if set(splits) != set(EXPECTED_SPLITS):
        raise ValueError("only train and validation may be executable splits")
    split_counts: dict[str, int] = {}
    for split, (seed_base, repeats) in EXPECTED_SPLITS.items():
        definition = _mapping(splits[split], f"splits.{split}")
        if (definition.get("seed_base"), definition.get("repeats_per_family_density")) != (
            seed_base,
            repeats,
        ):
            raise ValueError(f"{split} must use seed base {seed_base} and {repeats} repeats")
        split_counts[split] = len(families) * len(densities) * repeats
    reserved_test = _mapping(config.get("reserved_held_out_test"), "reserved_held_out_test")
    if reserved_test.get("enabled") is not False:
        raise ValueError("held-out test must remain disabled before protocol freeze")
    if (
        reserved_test.get("seed_base"),
        reserved_test.get("repeats_per_family_density"),
    ) != RESERVED_TEST:
        raise ValueError("reserved test must retain seed base 97000 and five repeats")
    invariants = _mapping(config.get("invariants"), "invariants")
    if invariants.get("dagger_sources") != ["train"]:
        raise ValueError("DAgger sources must be train only")
    if invariants.get("model_selection_sources") != ["train", "validation"]:
        raise ValueError("model selection must use train and validation only")
    if "moderate_v6_test" not in invariants.get("forbidden_sources", []):
        raise ValueError("moderate_v6_test must be explicitly excluded")
    return {
        "benchmark_id": config["benchmark_id"],
        "config_path": str(config_path.relative_to(ROOT)),
        "config_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "families": audited_families,
        "densities": densities,
        "planned_conditions_by_split": split_counts,
        "planned_condition_count": sum(split_counts.values()),
        "held_out_test_materialized": False,
        "audit_status": "PASS",
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="optional audit JSON path")
    args = parser.parse_args(argv)
    report = audit(args.config.resolve())
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
