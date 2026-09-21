#!/usr/bin/env python3
"""Preflight one opt-in, train-only upstream-mask telemetry smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FROZEN_MARKERS = ("moderate_v6", "outputs/moderate/final", "checkpoints/final")
RUNTIME_SOURCE_PATHS = (
    "packages/ramp_core/ramp_core/action_mask.py",
    "packages/ramp_core/ramp_core/planning/online.py",
    "packages/ramp_core/ramp_core/recovery/mask_trace.py",
    "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py",
    "scripts/arena/run_baseline_episode.sh",
    "scripts/arena/run_baseline_episode_inner.sh",
)


def _normalized_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def preflight(
    root: Path,
    scenario: Path,
    episode_id: str,
    *,
    allow_validation: bool = False,
) -> dict[str, Any]:
    scenario_path = scenario if scenario.is_absolute() else root / scenario
    scenario_path = scenario_path.resolve()
    root = root.resolve()
    try:
        relative_scenario = scenario_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("scenario must be inside the project root") from error
    if any(marker in relative_scenario for marker in FROZEN_MARKERS):
        raise ValueError("refusing to use a frozen scenario or evidence path")
    if not scenario_path.is_file():
        raise FileNotFoundError(scenario_path)
    scenario_data = json.loads(scenario_path.read_text(encoding="utf-8"))
    metadata = scenario_data.get("ramp_metadata", {})
    allowed_splits = {"train", "validation"} if allow_validation else {"train"}
    if metadata.get("split") not in allowed_splits:
        allowed = " or ".join(sorted(allowed_splits))
        raise ValueError(f"mask-trace smoke requires a {allowed} split")
    if not episode_id.strip():
        raise ValueError("episode_id must not be empty")
    if any(marker in episode_id for marker in FROZEN_MARKERS):
        raise ValueError("episode_id contains a frozen marker")
    existing = [
        root / "data/raw" / f"{episode_id}.jsonl",
        root / "data/raw" / f"{episode_id}.outcome.json",
    ]
    if any(path.exists() for path in existing):
        raise FileExistsError("refusing to overwrite an existing local episode")

    manager = root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
    action_mask = root / "packages/ramp_core/ramp_core/action_mask.py"
    online = root / "packages/ramp_core/ramp_core/planning/online.py"
    wrapper = root / "scripts/arena/run_baseline_episode.sh"
    runtime = root / "scripts/arena/run_baseline_episode_inner.sh"
    required = tuple(root / relative for relative in RUNTIME_SOURCE_PATHS)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing runtime files: {missing}")
    manager_text = manager.read_text(encoding="utf-8")
    action_mask_text = action_mask.read_text(encoding="utf-8")
    online_text = online.read_text(encoding="utf-8")
    wrapper_text = wrapper.read_text(encoding="utf-8")
    runtime_text = runtime.read_text(encoding="utf-8")
    contract_checks = {
        "ros_parameter_defaults_false": (
            'self.declare_parameter("enable_upstream_mask_trace", False)' in manager_text
        ),
        "wrapper_defaults_zero": (
            'mask_trace="${RAMP_ENABLE_UPSTREAM_MASK_TRACE:-0}"' in wrapper_text
        ),
        "runtime_forwards_switch": (
            '-p enable_upstream_mask_trace:="${upstream_mask_trace_ros_value}"'
            in runtime_text
        ),
        "runtime_converts_switch_to_bool": (
            "upstream_mask_trace_ros_value=false" in runtime_text
            and "upstream_mask_trace_ros_value=true" in runtime_text
        ),
        "original_scan_predicates_traced": (
            "diagnostics=scan_diagnostics" in manager_text
            and "mask_scan_predicates directional_pass=" in manager_text
            and '"directional_pass": tuple(directional_pass_ids)' in action_mask_text
            and '"capsule_pass": tuple(capsule_pass_ids)' in action_mask_text
            and '"category": "initial_overlap_approaching"' in online_text
            and '"minimum_segment_clearance_m"' in online_text
        ),
    }
    if not all(contract_checks.values()):
        raise RuntimeError(f"mask-trace launch contract incomplete: {contract_checks}")
    command = (
        "RAMP_SOURCE_POLICY=pgrr "
        "RAMP_ENABLE_UPSTREAM_MASK_TRACE=1 "
        f"RAMP_EPISODE_ID={episode_id} "
        "RAMP_EPISODE_TIMEOUT_S=90 "
        f"SCENARIO={relative_scenario} "
        "scripts/arena/run_baseline_episode.sh"
    )
    return {
        "ready": True,
        "scenario": relative_scenario,
        "scenario_id": metadata.get("scenario_id"),
        "split": metadata.get("split"),
        "map_id": metadata.get("map_id"),
        "seed": metadata.get("seed"),
        "episode_id": episode_id,
        "timeout_s": 90,
        "source_policy": "pgrr",
        "trace_enabled": True,
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "allow_validation": allow_validation,
        "contract_checks": contract_checks,
        "runtime_source_normalized_sha256": {
            relative: _normalized_sha256(root / relative)
            for relative in RUNTIME_SOURCE_PATHS
        },
        "command": command,
        "frozen_markers_rejected": list(FROZEN_MARKERS),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-validation",
        action="store_true",
        help="permit a non-frozen validation scenario; test remains forbidden",
    )
    args = parser.parse_args()
    result = preflight(
        args.root,
        args.scenario,
        args.episode_id,
        allow_validation=args.allow_validation,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
