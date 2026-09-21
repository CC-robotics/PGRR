#!/usr/bin/env python3
"""Audit whether two train-only anchor geometries implement their named events."""

from __future__ import annotations

import argparse
import json
import math
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any


def _distance(first: list[float], second: list[float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _point_to_axis_segment(
    point: list[float], start: list[float], goal: list[float]
) -> dict[str, Any]:
    dx = goal[0] - start[0]
    dy = goal[1] - start[1]
    squared = dx * dx + dy * dy
    if squared <= 0.0:
        raise ValueError("robot start and goal must differ")
    fraction = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared
    clipped = min(1.0, max(0.0, fraction))
    closest = [start[0] + clipped * dx, start[1] + clipped * dy]
    return {
        "projection_fraction": fraction,
        "inside_segment": 0.0 <= fraction <= 1.0,
        "lateral_offset_m": _distance(point, closest),
    }


def _corridor_wall_centerline_spacing(static: list[dict[str, Any]]) -> float | None:
    south = [float(item["pos"][1]) for item in static if item.get("name", "").startswith("south_")]
    north = [float(item["pos"][1]) for item in static if item.get("name", "").startswith("north_")]
    if not south or not north:
        return None
    return median(north) - median(south)


def audit(path: Path) -> dict[str, Any]:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    metadata = scenario.get("ramp_metadata", {})
    family = str(metadata.get("family", ""))
    robots = scenario.get("robots", [])
    actors = scenario.get("obstacles", {}).get("dynamic", [])
    if len(robots) != 1 or len(actors) != 1:
        raise ValueError("anchor audit requires exactly one robot and one dynamic actor")
    start = robots[0]["start"]
    goal = robots[0]["goal"]
    actor = actors[0]
    waypoints = actor.get("waypoints", [])
    if len(waypoints) < 2:
        raise ValueError("anchor actor must provide at least two waypoints")
    route_start = waypoints[0]
    route_end = waypoints[-1]
    common = {
        "source": str(path),
        "scenario_id": metadata.get("scenario_id"),
        "family": family,
        "split": metadata.get("split"),
        "prototype_status": metadata.get("prototype_status"),
        "robot_path_length_m": _distance(start, goal),
        "actor_route_length_m": sum(
            _distance(first, second) for first, second in pairwise(waypoints)
        ),
        "actor_cyclic_goals": bool(actor.get("cyclic_goals", False)),
        "wall_centerline_spacing_m": _corridor_wall_centerline_spacing(
            scenario.get("obstacles", {}).get("static", [])
        ),
        "actor_start_relative_to_robot_path": _point_to_axis_segment(route_start, start, goal),
        "actor_end_relative_to_robot_path": _point_to_axis_segment(route_end, start, goal),
        "actor_end_distance_to_robot_goal_m": _distance(route_end, goal),
    }
    limitations = [str(item) for item in metadata.get("limitations", [])]
    if family == "lead_pedestrian_sudden_stop":
        common["semantic_checks"] = {
            "terminal_endpoint_on_robot_path": (
                common["actor_end_relative_to_robot_path"]["inside_segment"]
                and common["actor_end_relative_to_robot_path"]["lateral_offset_m"] < 1.0e-6
            ),
            "explicit_stop_time_or_trigger": False,
            "explicit_stop_duration": False,
            "terminal_stop_may_persist_on_route": not common["actor_cyclic_goals"],
        }
        common["interpretation"] = (
            "The file encodes a lead actor that ends on the robot centerline, but not an "
            "independently timed sudden-stop event or a bounded release. Treat it as a "
            "persistent-blockage stress prototype until event timing is implemented."
        )
    elif family == "goal_approach_lateral_interruption":
        start_projection = _point_to_axis_segment(route_start, start, goal)
        end_projection = _point_to_axis_segment(route_end, start, goal)
        crosses_axis = (
            start_projection["inside_segment"]
            and end_projection["inside_segment"]
            and (route_start[1] - start[1]) * (route_end[1] - start[1]) <= 0.0
        )
        common["semantic_checks"] = {
            "route_crosses_robot_path": crosses_axis,
            "explicit_robot_approach_trigger": False,
            "one_shot_interruption": not common["actor_cyclic_goals"],
            "occlusion_implemented": not any(
                "occlusion not implemented" in item for item in limitations
            ),
        }
        common["interpretation"] = (
            "The file encodes a cyclic crossing near the goal, not an approach-triggered "
            "one-shot interruption; its own metadata also says occlusion is absent. Treat "
            "it as a spatial crossing stress prototype, not the named causal event."
        )
    else:
        raise ValueError(f"unsupported anchor family: {family}")
    return common


def analyze(paths: list[Path]) -> dict[str, Any]:
    scenarios = [audit(path) for path in paths]
    return {
        "claim_boundary": "static schema and geometry audit; no simulator counterfactual",
        "diagnostic_only": True,
        "algorithm_change_authorized": False,
        "scenario_replacement_authorized": False,
        "scenarios": scenarios,
        "aggregate": {
            "scenario_count": len(scenarios),
            "train_only_count": sum(item["split"] == "train" for item in scenarios),
            "draft_prototype_count": sum(
                "draft" in str(item["prototype_status"])
                or "pending" in str(item["prototype_status"])
                for item in scenarios
            ),
            "named_event_fully_encoded_count": 0,
        },
        "recommendation": (
            "retain both artifacts as stress prototypes and historical diagnostics; build "
            "event-controlled train/validation variants before algorithm changes or core claims"
        ),
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Two-anchor scenario-semantic audit",
        "",
        "## Boundary",
        "",
        report["claim_boundary"] + ".",
        "",
        "## Findings",
        "",
    ]
    for scenario in report["scenarios"]:
        lines.extend(
            [
                f"### {scenario['family']}",
                "",
                f"- Scenario: `{scenario['scenario_id']}`",
                f"- Prototype status: `{scenario['prototype_status']}`",
                f"- Cyclic actor: `{scenario['actor_cyclic_goals']}`",
                f"- Actor route length: {scenario['actor_route_length_m']:.3f} m",
                "- Actor endpoint to robot goal: "
                f"{scenario['actor_end_distance_to_robot_goal_m']:.3f} m",
                f"- Semantic checks: `{json.dumps(scenario['semantic_checks'], sort_keys=True)}`",
                f"- Interpretation: {scenario['interpretation']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommendation",
            "",
            report["recommendation"] + ".",
            "",
            "These files remain useful as stress tests and provenance. They should not be",
            "discarded or silently replaced, and they should not drive a safety-threshold change.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, action="append", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.scenario)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(report, args.markdown_output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
