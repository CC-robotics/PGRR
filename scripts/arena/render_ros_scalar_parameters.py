#!/usr/bin/env python3
"""Render a flat YAML mapping as one ROS 2 CLI argument per output line.

The output alternates ``-p`` and ``name:=value`` lines so Bash ``readarray``
can preserve each argument without invoking ``eval``. Runtime configuration
files are intentionally restricted to scalar values; accepting nested data
would make the ROS parameter interpretation ambiguous.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import yaml

_PARAMETER_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _serialize(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("floating-point ROS parameters must be finite")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported ROS parameter value type: {type(value).__name__}")


def render(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"parameter file does not exist: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("parameter file must contain a non-empty flat mapping")

    arguments: list[str] = []
    for raw_name, value in payload.items():
        if not isinstance(raw_name, str) or not _PARAMETER_NAME.fullmatch(raw_name):
            raise ValueError(f"invalid ROS parameter name: {raw_name!r}")
        arguments.extend(("-p", f"{raw_name}:={_serialize(value)}"))
    return arguments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    for argument in render(args.config):
        print(argument)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
