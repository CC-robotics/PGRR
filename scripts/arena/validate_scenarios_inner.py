#!/usr/bin/env python3
"""Validate generated files with the Arena parser installed in the runtime image."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from arena_simulation_setup.shared import DynamicObstacle, Obstacle
from arena_simulation_setup.world import RobotGoal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_root", type=Path)
    args = parser.parse_args()
    files = sorted(args.scenario_root.glob("*.json"))
    if not files:
        raise SystemExit("no generated scenarios found")
    validated = 0
    for path in files:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "ramp_metadata" not in obj:
            continue
        robots = [RobotGoal.parse(item) for item in obj.get("robots", [])]
        static = [Obstacle.parse(item) for item in obj.get("obstacles", {}).get("static", [])]
        dynamic = [
            DynamicObstacle.parse(item) for item in obj.get("obstacles", {}).get("dynamic", [])
        ]
        if len(robots) != 1 or not dynamic:
            raise RuntimeError(f"invalid parsed counts in {path.name}")
        for actor in dynamic:
            actor.model.get()
        for obstacle in static:
            obstacle.model.get()
        validated += 1
    if validated == 0:
        raise RuntimeError("no catalog scenarios with ramp_metadata found")
    print(f"Arena parser validation PASS: {validated} scenarios")


if __name__ == "__main__":
    main()
