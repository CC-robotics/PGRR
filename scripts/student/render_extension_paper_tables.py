#!/usr/bin/env python3
"""Render non-result paper-material tables from the extension planning catalog.

The output is intentionally limited to scenario-design and split-protocol
tables.  It never reads evaluation results, runs the simulator, or writes a
held-out test manifest.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"


def _config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("benchmark_id") != "pgrr_extension_v1":
        raise ValueError("expected a pgrr_extension_v1 planning catalog")
    if payload.get("status") != "planning_train_validation_only":
        raise ValueError("catalog must remain train/validation planning only")
    return payload


def _format_values(values: object) -> str:
    if isinstance(values, list):
        return ", ".join(str(value) for value in values)
    return str(values)


def scenario_variable_table(config: dict[str, Any]) -> str:
    """Create a result-free Markdown table for the extension scenario settings."""
    lines = [
        "# PGRR extension v1: scenario variables",
        "",
        "> Draft design material only. This table contains no simulator or evaluation results.",
        "",
        "| Family | Interaction question | Variable | Candidate values |",
        "|---|---|---|---|",
    ]
    for family in config["families"]:
        purpose = str(family["purpose"])
        first = True
        for name, values in dict(family["variables"]).items():
            label = str(family["id"]) if first else ""
            question = purpose if first else ""
            lines.append(f"| {label} | {question} | {name} | {_format_values(values)} |")
            first = False
    density_levels = ", ".join(
        f"{name} = {count} pedestrian(s)" for name, count in config["densities"].items()
    )
    lines += [
        "",
        "Common density levels: " + density_levels + ".",
        "Current map note: map_empty is used only for early train/validation smoke; "
        "this is not map-disjoint generalization evidence.",
    ]
    return "\n".join(lines) + "\n"


def split_seed_table(config: dict[str, Any]) -> str:
    """Create a protocol table while keeping held-out test non-materialized."""
    lines = [
        "# PGRR extension v1: split and seed protocol",
        "",
        "> Protocol draft only. No held-out test conditions are materialized by this script.",
        "",
        "| Split | Seed base | Repeats per family-density cell | Allowed use |",
        "|---|---:|---:|---|",
    ]
    for name, split in config["splits"].items():
        row = (
            f"| {name} | {split['seed_base']} | "
            f"{split['repeats_per_family_density']} | {split['purpose']} |"
        )
        lines.append(row)
    test = config["reserved_held_out_test"]
    lines.append(
        f"| held_out_test (reserved, not materialized) | {test['seed_base']} | "
        f"{test['repeats_per_family_density']} | {test['purpose']} |"
    )
    lines += [
        "",
        f"Seed formula: `{config['seed_formula']}`.",
        "Split unit: complete episode. DAgger sources: train only. "
        "Model selection sources: train and validation only.",
        "No scenario/seed/configuration hash/geometry may overlap across splits; "
        "moderate_v6_test remains excluded.",
    ]
    return "\n".join(lines) + "\n"


def render(config_path: Path, output_dir: Path) -> tuple[Path, Path]:
    config = _config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    variables_path = output_dir / "pgrr_extension_v1_scenario_variables.md"
    split_path = output_dir / "pgrr_extension_v1_split_seed_protocol.md"
    variables_path.write_text(scenario_variable_table(config), encoding="utf-8")
    split_path.write_text(split_seed_table(config), encoding="utf-8")
    return variables_path, split_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    variables_path, split_path = render(args.config.resolve(), args.output_dir)
    print(f"Wrote {variables_path}")
    print(f"Wrote {split_path}")


if __name__ == "__main__":
    main()
