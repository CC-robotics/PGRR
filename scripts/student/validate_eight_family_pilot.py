"""Validate the executable, train-only eight-family development pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(config_path: Path = DEFAULT_CONFIG, root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if config.get("status") != "executable_development_pilot":
        errors.append("status must be executable_development_pilot")
    if config.get("scope") != "train_only_development_not_final_evaluation":
        errors.append("scope must remain train-only development")
    boundary = config.get("claim_boundary", {})
    if boundary.get("held_out_test_materialized") is not False:
        errors.append("held-out test must remain unmaterialized")
    if boundary.get("no_training") is not True or boundary.get("no_threshold_tuning") is not True:
        errors.append("pilot must forbid training and threshold tuning")

    checkpoint = config.get("checkpoint", {})
    checkpoint_path = root / str(checkpoint.get("path", ""))
    if not checkpoint_path.is_file():
        errors.append(f"checkpoint missing: {checkpoint_path}")
    elif _sha256(checkpoint_path) != checkpoint.get("sha256"):
        errors.append("checkpoint sha256 mismatch")

    families = config.get("families", [])
    if len(families) != 8:
        errors.append(f"expected 8 families, found {len(families)}")
    indices = [item.get("family_index") for item in families]
    if sorted(indices) != list(range(8)):
        errors.append(f"family indices must be 0..7, found {indices}")
    if len({item.get("id") for item in families}) != len(families):
        errors.append("family ids must be unique")

    density_index = config.get("density_index", {})
    scenario_ids: set[str] = set()
    verified_files = 0
    for item in families:
        label = str(item.get("id", "<missing>"))
        if item.get("split") != "train":
            errors.append(f"{label}: only train scenarios are permitted")
        density = item.get("density")
        expected_density_index = density_index.get(density)
        if item.get("density_index") != expected_density_index:
            errors.append(f"{label}: density_index mismatch")
        expected_seed = 91000 + 100 * int(item.get("family_index", -100)) + 10 * int(
            item.get("density_index", -100)
        ) + int(item.get("repeat_index", -100))
        if item.get("seed") != expected_seed:
            errors.append(f"{label}: seed {item.get('seed')} != {expected_seed}")
        if item.get("actual_motion_verified") is not True:
            errors.append(f"{label}: actual motion has not been verified")

        scenario_id = item.get("scenario_id")
        if scenario_id in scenario_ids:
            errors.append(f"duplicate scenario_id: {scenario_id}")
        scenario_ids.add(scenario_id)
        path = root / str(item.get("scenario_path", ""))
        if not path.is_file():
            errors.append(f"{label}: scenario missing: {path}")
            continue
        if _sha256(path) != item.get("sha256"):
            errors.append(f"{label}: scenario sha256 mismatch")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = payload.get("ramp_metadata", {})
        expected = {
            "family": item.get("id"),
            "density": density,
            "split": "train",
            "seed": item.get("seed"),
            "scenario_id": scenario_id,
            "map_id": config.get("map_id"),
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                errors.append(f"{label}: metadata {key} mismatch")
        if len(payload.get("robots", [])) != 1:
            errors.append(f"{label}: expected exactly one robot")
        if not payload.get("obstacles", {}).get("dynamic"):
            errors.append(f"{label}: expected at least one dynamic actor")
        verified_files += 1

    phases = config.get("execution_phases", [])
    attempts = sum(int(p.get("expected_episode_attempts", 0)) for p in phases)
    if attempts != 32:
        errors.append(f"expected 32 planned paired attempts, found {attempts}")

    report = {
        "benchmark_id": config.get("benchmark_id"),
        "valid": not errors,
        "family_count": len(families),
        "verified_scenario_files": verified_files,
        "planned_episode_attempts": attempts,
        "held_out_test_materialized": boundary.get("held_out_test_materialized"),
        "errors": errors,
    }
    if errors:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args(argv)
    report = validate(args.config.resolve(), args.root.resolve())
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
