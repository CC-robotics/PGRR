#!/usr/bin/env python3
"""Materialize the TaskGenerator view of a RAMP scenario atomically.

RAMP's deterministic Gazebo actor controller owns the dynamic pedestrian
proxies.  TaskGenerator still owns the robot reset and static obstacles, so it
receives an otherwise identical scenario with its native dynamic-obstacle list
removed.  The original scenario remains untouched for provenance and for the
actor controller.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _load_scenario(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scenario root must be a JSON object")
    obstacles = payload.get("obstacles")
    if not isinstance(obstacles, dict):
        raise ValueError("scenario obstacles must be a JSON object")
    if not isinstance(obstacles.get("dynamic"), list):
        raise ValueError("scenario obstacles.dynamic must be a JSON list")
    return payload


def materialize_runtime_scenario(source: Path, output: Path) -> None:
    """Write an atomic TaskGenerator scenario without native dynamic actors."""

    scenario = _load_scenario(source)
    scenario["obstacles"]["dynamic"] = []

    output_parent = output.parent
    if not output_parent.is_dir():
        raise FileNotFoundError(f"runtime scenario directory does not exist: {output_parent}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(scenario, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            os.fchmod(temporary.fileno(), 0o644)
        os.replace(temporary_path, output)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    materialize_runtime_scenario(args.source, args.output)


if __name__ == "__main__":
    main()
