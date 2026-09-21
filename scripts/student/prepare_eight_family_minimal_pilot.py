"""Build the pinned Base/PGRR execution plan for the eight-family pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from .validate_eight_family_pilot import DEFAULT_CONFIG, ROOT, validate
else:
    from validate_eight_family_pilot import DEFAULT_CONFIG, ROOT, validate


DEFAULT_OUTPUT = ROOT / "outputs/student/eight_family_pilot"
FIELDS = [
    "order",
    "family_index",
    "family",
    "method",
    "episode_id",
    "scenario_id",
    "scenario_path",
    "scenario_sha256",
    "runtime_scenario_path",
    "seed",
    "timeout_s",
    "ros_domain_id",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan(config_path: Path = DEFAULT_CONFIG, root: Path = ROOT) -> dict[str, Any]:
    validation = validate(config_path, root)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    rows = []
    order = 0
    for family in config["families"]:
        for method_index, method in enumerate(("base", "pgrr")):
            episode_id = (
                f"pgrr_extpilot_f{family['family_index']:02d}_{family['id']}_"
                f"{family['density']}_train_r00_s{family['seed']}_{method}"
            )
            rows.append(
                {
                    "order": order,
                    "family_index": family["family_index"],
                    "family": family["id"],
                    "method": method,
                    "episode_id": episode_id,
                    "scenario_id": family["scenario_id"],
                    "scenario_path": family["scenario_path"],
                    "scenario_sha256": family["sha256"],
                    "runtime_scenario_path": (
                        "outputs/student/eight_family_pilot/scenarios/"
                        f"{family['scenario_id']}.json"
                    ),
                    "seed": family["seed"],
                    "timeout_s": 90,
                    "ros_domain_id": 101 + 2 * family["family_index"] + method_index,
                }
            )
            order += 1
    return {
        "schema_version": 1,
        "benchmark_id": config["benchmark_id"],
        "scope": config["scope"],
        "config_path": str(config_path.relative_to(root)).replace("\\", "/"),
        "config_sha256": _sha256(config_path),
        "checkpoint": config["checkpoint"],
        "attempt_count": len(rows),
        "methods": ["base", "pgrr"],
        "paired_by": config["paired_by"],
        "automatic_retry": False,
        "rows": rows,
        "validation": validation,
    }


def _render_tsv(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _write_reproducible(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FileExistsError(f"refusing to replace a different pinned plan: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Byte writes keep the TSV LF-only when it crosses from Windows into WSL.
    path.write_bytes(text.encode("utf-8"))


def write_plan(plan: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    json_path = output_root / "minimal_pair_plan.json"
    tsv_path = output_root / "minimal_pair_plan.tsv"
    _write_reproducible(json_path, json.dumps(plan, indent=2, sort_keys=True) + "\n")
    _write_reproducible(tsv_path, _render_tsv(plan["rows"]))
    return json_path, tsv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    plan = build_plan(args.config.resolve(), args.root.resolve())
    paths = write_plan(plan, args.output_root.resolve())
    summary = {"attempt_count": plan["attempt_count"], "outputs": [str(p) for p in paths]}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
