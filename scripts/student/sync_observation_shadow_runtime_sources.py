#!/usr/bin/env python3
"""Safely synchronize the five preflight-pinned shadow runtime sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ALLOWED_PATHS = {
    "packages/ramp_core/ramp_core/recovery/observation_builder.py": 0o644,
    "packages/ramp_core/ramp_core/recovery/observation_shadow.py": 0o644,
    "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py": 0o644,
    "scripts/arena/run_baseline_episode.sh": 0o755,
    "scripts/arena/run_baseline_episode_inner.sh": 0o755,
}


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sync(
    manifest_path: Path,
    source_root: Path,
    runtime_root: Path,
    backup_root: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("runtime_source_normalized_sha256")
    if not isinstance(expected, dict) or set(expected) != set(ALLOWED_PATHS):
        raise ValueError("manifest source set does not match the five-file allowlist")
    if backup_root.exists():
        raise FileExistsError(f"backup root already exists: {backup_root}")
    if runtime_root.resolve() == source_root.resolve():
        raise ValueError("source and runtime roots must differ")

    prepared: list[tuple[str, bytes, Path, Path]] = []
    for relative in sorted(ALLOWED_PATHS):
        source = source_root / relative
        target = runtime_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.is_symlink():
            raise ValueError(f"refusing to replace symlink: {target}")
        content = _normalized_bytes(source)
        if _digest(content) != expected[relative]:
            raise ValueError(f"source hash no longer matches preflight: {relative}")
        prepared.append((relative, content, source, target))

    records: list[dict[str, Any]] = []
    for relative, content, _source, target in prepared:
        backup = backup_root / relative
        existed = target.is_file()
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(ALLOWED_PATHS[relative])
        actual = _digest(_normalized_bytes(target))
        records.append(
            {
                "path": relative,
                "target_existed": existed,
                "backup": str(backup) if existed else None,
                "expected_sha256": expected[relative],
                "actual_sha256": actual,
                "matches": actual == expected[relative],
                "mode": oct(ALLOWED_PATHS[relative]),
            }
        )

    return {
        "synchronized": all(item["matches"] for item in records),
        "episode_id": manifest.get("episode_id"),
        "source_root": str(source_root.resolve()),
        "runtime_root": str(runtime_root.resolve()),
        "backup_root": str(backup_root.resolve()),
        "line_endings": "LF",
        "file_count": len(records),
        "files": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = sync(
        args.manifest, args.source_root, args.runtime_root, args.backup_root
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["synchronized"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
