#!/usr/bin/env python3
"""Compare the unused observation builder with the current inline node contract."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.observations import (
    RecoveryObservation,
    navigation_path_or_goal,
    select_local_path_waypoints,
)
from ramp_core.recovery.observation_builder import RecoveryObservationBuilder
from ramp_core.recovery.observation_shadow import (
    ARRAY_FIELDS,
    ObservationShadowAccumulator,
    ObservationShadowComparator,
)
from ramp_core.types import FailurePrediction, PlannerStatus, Pose2D, Velocity2D


def legacy_inline_reference(**values: Any) -> RecoveryObservation:
    """Independent transcription of ``RecoveryManagerNode._observation``."""
    pose, goal = values["pose"], values["goal"]
    distance = math.dist((pose.x, pose.y), (goal.x, goal.y))
    bearing = math.atan2(goal.y - pose.y, goal.x - pose.x) - pose.yaw
    bearing = math.atan2(math.sin(bearing), math.cos(bearing))
    points = navigation_path_or_goal(values["task_path"], (goal.x, goal.y))
    waypoints = select_local_path_waypoints(points, pose)
    lidar = list(values["lidar_history"])
    lidar = [lidar[0]] * (5 - len(lidar)) + lidar
    progress = list(values["distance_history"])
    progress = [distance] * (10 - len(progress)) + progress
    angular = list(values["angular_velocity_history"])
    angular = [0.0] * (10 - len(angular)) + angular
    velocity = values["velocity"]
    return RecoveryObservation(
        lidar=np.asarray(lidar[-5:], dtype=np.float32),
        goal_polar=np.asarray([distance, bearing], dtype=np.float32),
        path_waypoints=waypoints,
        robot_velocity=np.asarray([velocity.linear, velocity.angular], dtype=np.float32),
        base_action=np.asarray(values["base_action"], dtype=np.float32).copy(),
        progress_history=np.asarray(progress[-10:], dtype=np.float32),
        angular_velocity_history=np.asarray(angular[-10:], dtype=np.float32),
        planner_status=values["planner_status"],
        failure_prediction=values["failure_prediction"],
    )


def _case(rng: np.random.Generator, index: int) -> dict[str, Any]:
    pose = Pose2D(*rng.uniform([-3.0, -3.0, -math.pi], [3.0, 3.0, math.pi]))
    goal = Pose2D(*rng.uniform([-5.0, -5.0, -math.pi], [5.0, 5.0, math.pi]))
    path_length = (0, 1, 3, 12)[index % 4]
    task_path = tuple(tuple(point) for point in rng.uniform(-5.0, 5.0, (path_length, 2)))
    lidar_length = (1, 2, 5, 7)[index % 4]
    lidar = [rng.uniform(0.05, 12.0, 180).astype(np.float32) for _ in range(lidar_length)]
    distance_length = (0, 1, 9, 12)[index % 4]
    angular_length = (0, 3, 10, 13)[index % 4]
    probabilities = rng.dirichlet(np.ones(5))[:4]
    return {
        "pose": pose,
        "velocity": Velocity2D(*rng.uniform([-0.5, -1.5], [1.0, 1.5])),
        "goal": goal,
        "task_path": task_path,
        "lidar_history": lidar,
        "distance_history": rng.uniform(0.0, 20.0, distance_length).tolist(),
        "angular_velocity_history": rng.uniform(-2.0, 2.0, angular_length).tolist(),
        "base_action": rng.uniform([-0.5, -1.5], [1.0, 1.5]),
        "planner_status": PlannerStatus(index % len(PlannerStatus)),
        "failure_prediction": FailurePrediction(*probabilities),
    }


def run_probe(*, seed: int, case_count: int) -> dict[str, Any]:
    if case_count <= 0:
        raise ValueError("case count must be positive")
    rng = np.random.default_rng(seed)
    comparator = ObservationShadowComparator(enabled=True)
    accumulator = ObservationShadowAccumulator()
    field_max = {field: 0.0 for field in ARRAY_FIELDS}
    cases = []
    for index in range(case_count):
        values = _case(rng, index)
        reference = legacy_inline_reference(**values)
        comparison = comparator.compare(
            reference, lambda values=values: RecoveryObservationBuilder.build(**values)
        )
        assert comparison is not None
        accumulator.record(comparison)
        errors = comparison.field_max_abs_error
        for field, error in errors.items():
            assert error is not None
            field_max[field] = max(field_max[field], error)
        cases.append(
            {
                "case_index": index,
                "path_length": len(values["task_path"]),
                "lidar_history_length": len(values["lidar_history"]),
                "distance_history_length": len(values["distance_history"]),
                "angular_history_length": len(values["angular_velocity_history"]),
                "field_max_abs_error": errors,
                "metadata_equal": comparison.metadata_equal,
                "shadow_equivalent": comparison.equivalent,
            }
        )
    equivalent = all(value == 0.0 for value in field_max.values()) and all(
        case["metadata_equal"] for case in cases
    )
    return {
        "schema_version": 1,
        "seed": seed,
        "case_count": case_count,
        "equivalent": equivalent,
        "field_max_abs_error": field_max,
        "cases": cases,
        "shadow_summary": accumulator.as_dict(),
        "claim_boundary": "offline characterization only; ROS node not rewired",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cases", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_probe(seed=args.seed, case_count=args.cases)
    if not report["equivalent"]:
        raise RuntimeError("observation builder differs from inline reference")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
