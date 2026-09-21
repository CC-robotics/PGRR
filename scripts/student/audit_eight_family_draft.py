#!/usr/bin/env python3
"""Audit the eight-family PGRR extension design without compiling or running it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
PLANNED_SPLITS = ("train", "validation")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def audit(config_path: Path) -> dict[str, Any]:
    """Check identity, eight-family coverage, deterministic seeds, and test boundary."""
    config = _mapping(yaml.safe_load(config_path.read_text(encoding="utf-8")), "config")
    if config.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("catalog must remain a non-executable train/validation draft")
    families = config.get("families")
    if not isinstance(families, list) or len(families) != 8:
        raise ValueError("the draft must contain exactly eight scenario families")
    indices = [family.get("family_index") for family in families if isinstance(family, dict)]
    if sorted(indices) != list(range(8)):
        raise ValueError("family_index values must be the complete range 0..7")
    if any(not family.get("failure_target") or not family.get("variables") for family in families):
        raise ValueError("every family needs an intended failure target and variables")
    densities = _mapping(config.get("densities"), "densities")
    if densities != {"low": 1, "medium": 2, "high": 4}:
        raise ValueError("densities must be low/medium/high = 1/2/4")
    splits = _mapping(config.get("splits"), "splits")
    if set(splits) != set(PLANNED_SPLITS):
        raise ValueError("only train and validation may be planned")
    expected = {"train": (91000, 6), "validation": (93000, 3)}
    condition_keys: set[tuple[str, str, int]] = set()
    counts: dict[str, int] = {}
    for split, (base, repeats) in expected.items():
        definition = _mapping(splits[split], f"splits.{split}")
        if (definition.get("seed_base"), definition.get("repeats_per_family_density")) != (base, repeats):
            raise ValueError(f"{split} seed plan differs from the agreed protocol")
        count = 0
        for family in families:
            for density_index, density in enumerate(densities):
                for repeat in range(repeats):
                    seed = base + 100 * family["family_index"] + 10 * density_index + repeat
                    key = (family["id"], density, seed)
                    if key in condition_keys:
                        raise ValueError("duplicate family/density/seed combination")
                    condition_keys.add(key)
                    count += 1
        counts[split] = count
    reserved = _mapping(config.get("reserved_held_out_test"), "reserved_held_out_test")
    if reserved.get("enabled") is not False:
        raise ValueError("held-out test must remain disabled")
    invariants = _mapping(config.get("invariants"), "invariants")
    if invariants.get("dagger_sources") != ["train"]:
        raise ValueError("DAgger sources must remain train only")
    if invariants.get("model_selection_sources") != ["train", "validation"]:
        raise ValueError("model selection must remain train + validation only")
    if "moderate_v6_test" not in invariants.get("forbidden_sources", []):
        raise ValueError("moderate_v6_test must be excluded")
    return {
        "audit_status": "PASS",
        "benchmark_id": config["benchmark_id"],
        "family_count": len(families),
        "families": [family["id"] for family in families],
        "conditions_by_split": counts,
        "planned_condition_count": sum(counts.values()),
        "held_out_test_materialized": False,
        "executable": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.config.resolve())
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
