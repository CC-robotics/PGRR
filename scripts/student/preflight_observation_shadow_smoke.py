#!/usr/bin/env python3
"""Preflight one non-frozen, diagnostic-only observation-shadow smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FROZEN_MARKERS = ("moderate_v6", "outputs/moderate/final", "checkpoints/final")
RUNTIME_SOURCE_PATHS = (
    "packages/ramp_core/ramp_core/recovery/observation_builder.py",
    "packages/ramp_core/ramp_core/recovery/observation_shadow.py",
    "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py",
    "scripts/arena/run_baseline_episode.sh",
    "scripts/arena/run_baseline_episode_inner.sh",
)


def _normalized_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def preflight(root: Path, scenario: Path, episode_id: str) -> dict[str, Any]:
    root = root.resolve()
    scenario_path = scenario if scenario.is_absolute() else root / scenario
    scenario_path = scenario_path.resolve()
    try:
        relative_scenario = scenario_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("scenario must be inside the project root") from error
    if any(marker in relative_scenario for marker in FROZEN_MARKERS):
        raise ValueError("refusing to use a frozen scenario or evidence path")
    if not scenario_path.is_file():
        raise FileNotFoundError(scenario_path)
    metadata = json.loads(scenario_path.read_text(encoding="utf-8")).get("ramp_metadata", {})
    if metadata.get("split") not in {"train", "validation"}:
        raise ValueError("observation shadow smoke requires train or validation split")
    if not episode_id.strip() or any(marker in episode_id for marker in FROZEN_MARKERS):
        raise ValueError("episode_id is empty or contains a frozen marker")
    existing = [
        root / "data/raw" / f"{episode_id}.jsonl",
        root / "data/raw" / f"{episode_id}.outcome.json",
    ]
    if any(path.exists() for path in existing):
        raise FileExistsError("refusing to overwrite an existing local episode")

    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text(
        encoding="utf-8"
    )
    wrapper = (root / "scripts/arena/run_baseline_episode.sh").read_text(encoding="utf-8")
    runtime = (root / "scripts/arena/run_baseline_episode_inner.sh").read_text(
        encoding="utf-8"
    )
    checks = {
        "ros_parameter_defaults_false": (
            'self.declare_parameter("enable_observation_shadow", False)' in manager
        ),
        "legacy_observation_remains_authoritative": "return reference" in manager,
        "wrapper_defaults_zero": (
            'observation_shadow="${RAMP_ENABLE_OBSERVATION_SHADOW:-0}"' in wrapper
        ),
        "wrapper_validates_and_forwards": (
            "RAMP_ENABLE_OBSERVATION_SHADOW must be 0 or 1" in wrapper
            and "RAMP_ENABLE_OBSERVATION_SHADOW=${observation_shadow}" in wrapper
        ),
        "runtime_converts_and_forwards_bool": (
            "observation_shadow_ros_value=false" in runtime
            and "observation_shadow_ros_value=true" in runtime
            and '-p enable_observation_shadow:="${observation_shadow_ros_value}"' in runtime
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"observation-shadow launch contract incomplete: {checks}")
    command = (
        "RAMP_SOURCE_POLICY=pgrr "
        "RAMP_ENABLE_OBSERVATION_SHADOW=1 "
        f"RAMP_EPISODE_ID={episode_id} "
        "RAMP_EPISODE_TIMEOUT_S=90 "
        f"SCENARIO={relative_scenario} "
        "scripts/arena/run_baseline_episode.sh"
    )
    return {
        "ready": True,
        "diagnostic_only": True,
        "authoritative_path_changed": False,
        "scenario": relative_scenario,
        "scenario_id": metadata.get("scenario_id"),
        "split": metadata.get("split"),
        "map_id": metadata.get("map_id"),
        "seed": metadata.get("seed"),
        "episode_id": episode_id,
        "timeout_s": 90,
        "source_policy": "pgrr",
        "observation_shadow_enabled": True,
        "contract_checks": checks,
        "runtime_source_normalized_sha256": {
            relative: _normalized_sha256(root / relative)
            for relative in RUNTIME_SOURCE_PATHS
        },
        "command": command,
        "frozen_markers_rejected": list(FROZEN_MARKERS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = preflight(args.root, args.scenario, args.episode_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
