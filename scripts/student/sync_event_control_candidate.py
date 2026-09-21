#!/usr/bin/env python3
"""Safely sync the event-control runtime and one fixed candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ALLOWED_PATHS = {
    "packages/ramp_core/ramp_core/scenario/__init__.py": 0o644,
    "packages/ramp_core/ramp_core/scenario/contract.py": 0o644,
    "packages/ramp_core/ramp_core/scenario/events.py": 0o644,
    "packages/ramp_core/ramp_core/scenario/runtime.py": 0o644,
    "ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py": 0o644,
    "ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py": 0o644,
    "scripts/arena/run_baseline_episode.sh": 0o755,
    "scripts/arena/run_baseline_episode_inner.sh": 0o755,
    (
        "outputs/student/event_controlled_candidates/generated/arena/map_empty/"
        "closing_gap_open_release_v1_train_r00_s91410.json"
    ): 0o644,
}


def _normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sync(source_root: Path, runtime_root: Path, backup_root: Path) -> dict[str, Any]:
    """Copy only the allowlisted paths, backing up every existing target."""

    source_root = source_root.resolve()
    runtime_root = runtime_root.resolve()
    backup_root = backup_root.resolve()
    if source_root == runtime_root:
        raise ValueError("source and runtime roots must differ")
    if backup_root.exists():
        raise FileExistsError(f"backup root already exists: {backup_root}")

    prepared: list[tuple[str, bytes, Path]] = []
    for relative in sorted(ALLOWED_PATHS):
        source = source_root / relative
        target = runtime_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.is_symlink():
            raise ValueError(f"refusing to replace symlink: {target}")
        prepared.append((relative, _normalized(source), target))

    records: list[dict[str, Any]] = []
    for relative, content, target in prepared:
        backup = backup_root / relative
        existed = target.is_file()
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(ALLOWED_PATHS[relative])
        actual = _digest(_normalized(target))
        expected = _digest(content)
        records.append(
            {
                "path": relative,
                "target_existed": existed,
                "backup": str(backup) if existed else None,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "matches": actual == expected,
                "mode": oct(ALLOWED_PATHS[relative]),
            }
        )
    return {
        "synchronized": all(record["matches"] for record in records),
        "file_count": len(records),
        "line_endings": "LF",
        "source_root": str(source_root),
        "runtime_root": str(runtime_root),
        "backup_root": str(backup_root),
        "files": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = sync(args.source_root, args.runtime_root, args.backup_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
