#!/usr/bin/env python3
"""Audit failure-trigger coverage in non-frozen episode JSONL files.

Privileged human positions are used only as a diagnostic proxy.  They are not
policy observations and this script does not change detector thresholds.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


FAILURES = ("collision_risk", "freeze", "oscillation", "deadlock")


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _xy(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        x, y = _finite_number(value.get("x")), _finite_number(value.get("y"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _finite_number(value[0]), _finite_number(value[1])
    else:
        return None
    return (x, y) if x is not None and y is not None else None


def _human_positions(row: dict[str, Any]) -> Iterable[tuple[float, float]]:
    privileged = row.get("privileged") or {}
    positions = privileged.get("human_positions") or []
    if isinstance(positions, dict):
        positions = positions.values()
    for value in positions:
        point = _xy(value)
        if point is not None:
            yield point


def audit_rows(
    rows: list[dict[str, Any]], *, tau_on: float, privileged_close_m: float
) -> dict[str, Any]:
    states: Counter[str] = Counter()
    class_max = {name: 0.0 for name in FAILURES}
    class_crossings = {name: 0 for name in FAILURES}
    scores: list[float] = []
    obstacle_distances: list[float] = []
    human_distances: list[float] = []
    goal_distances: list[float] = []
    robot_points: list[tuple[float, float]] = []
    collision_rows = 0

    for row in rows:
        states[str(row.get("recovery_state", "UNKNOWN"))] += 1
        score = _finite_number(row.get("failure_score"))
        if score is not None:
            scores.append(score)
        predictions = row.get("failure_prediction") or []
        for index, name in enumerate(FAILURES):
            if index >= len(predictions):
                continue
            value = _finite_number(predictions[index])
            if value is None:
                continue
            class_max[name] = max(class_max[name], value)
            class_crossings[name] += int(value > tau_on)
        obstacle = _finite_number(row.get("nearest_obstacle_distance"))
        if obstacle is not None:
            obstacle_distances.append(obstacle)
        goal = _finite_number(row.get("distance_to_goal"))
        if goal is not None:
            goal_distances.append(goal)
        robot = _xy(row.get("robot_pose"))
        if robot is not None:
            robot_points.append(robot)
            for human in _human_positions(row):
                human_distances.append(math.dist(robot, human))
        collision_rows += int(bool(row.get("collision")))

    selector_active = any(state in states for state in {"1", "2", "3", "PENDING_RECOVERY", "RECOVERY", "REJOIN"})
    emergency_active = any(state in states for state in {"4", "EMERGENCY_STOP"})
    triggered = selector_active or emergency_active
    threshold_crossings = sum(value > tau_on for value in scores)
    min_human = min(human_distances, default=None)
    max_score = max(scores, default=0.0)
    if selector_active:
        diagnosis = "selector_recovery_triggered"
    elif emergency_active:
        diagnosis = "emergency_stop_only"
    elif threshold_crossings:
        diagnosis = "score_crossed_without_state_transition"
    elif min_human is not None and min_human < privileged_close_m:
        diagnosis = "privileged_close_without_threshold_crossing"
    elif max_score > 0.0:
        diagnosis = "subthreshold_failure_signal"
    else:
        diagnosis = "no_recorded_failure_signal"

    path_length = sum(math.dist(a, b) for a, b in zip(robot_points, robot_points[1:]))
    return {
        "sample_count": len(rows),
        "recovery_state_counts": dict(sorted(states.items())),
        "recovery_triggered": triggered,
        "selector_recovery_active": selector_active,
        "emergency_stop_active": emergency_active,
        "threshold_crossing_rows": threshold_crossings,
        "max_failure_score": max_score,
        "failure_class_max": class_max,
        "failure_class_crossing_rows": class_crossings,
        "min_observable_obstacle_distance_m": min(obstacle_distances, default=None),
        "min_privileged_robot_human_distance_m": min_human,
        "privileged_distance_pair_count": len(human_distances),
        "robot_path_length_m": path_length,
        "goal_distance_start_m": goal_distances[0] if goal_distances else None,
        "goal_distance_min_m": min(goal_distances, default=None),
        "collision_rows": collision_rows,
        "diagnosis": diagnosis,
    }


def audit_file(path: Path, *, tau_on: float, privileged_close_m: float) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = audit_rows(rows, tau_on=tau_on, privileged_close_m=privileged_close_m)
    result.update({"episode_id": path.stem, "source": path.as_posix()})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes", nargs="+", type=Path)
    parser.add_argument("--tau-on", required=True, type=float)
    parser.add_argument("--privileged-close-m", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    episodes = [
        audit_file(path, tau_on=args.tau_on, privileged_close_m=args.privileged_close_m)
        for path in args.episodes
    ]
    counts = Counter(item["diagnosis"] for item in episodes)
    payload = {
        "schema_version": 1,
        "scope": "non-frozen diagnostic only",
        "tau_on": args.tau_on,
        "privileged_close_m": args.privileged_close_m,
        "privileged_data_policy": "diagnostic proxy only; never a test observation",
        "episodes": episodes,
        "diagnosis_counts": dict(sorted(counts.items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
