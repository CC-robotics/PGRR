#!/usr/bin/env python3
"""Label recovery-relevant raw Arena states with the privileged rollout expert."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from ramp_core.action_mask import (
    apply_observable_scan_mask,
    apply_path_corridor_mask,
    compute_action_mask,
)
from ramp_core.observations import (
    HumanState,
    PrivilegedState,
    navigation_path_or_goal,
    select_local_path_waypoints,
)
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.expert import PlanningRecoveryExpert, update_expert_history
from ramp_core.planning.online import sanitize_near_field_returns
from ramp_core.recovery.options import (
    constrain_rejoin_actions,
    constrain_stalled_wait,
    failure_conditioned_wait_count,
)
from ramp_core.types import Pose2D, Velocity2D

ROOT = Path(__file__).resolve().parents[2]
LIDAR_FOV_RADIANS = math.radians(270.0)
JACKAL_EDGE_SELF_RETURN_MAX_M = 0.34


def _observable_lidar(row: dict[str, Any]) -> np.ndarray:
    values = sanitize_near_field_returns(
        row["lidar"],
        minimum_valid_range_m=0.0,
        bilateral_edge_self_return_max_m=JACKAL_EDGE_SELF_RETURN_MAX_M,
    )
    return np.nan_to_num(values, nan=12.0, posinf=12.0, neginf=0.0).astype(np.float32)


def _load(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not rows:
        raise ValueError(f"raw episode is empty: {path}")
    timestamps = np.asarray([row["timestamp"] for row in rows], dtype=np.float64)
    if np.any(np.diff(timestamps) <= 0.0):
        raise ValueError("raw timestamps must be strictly increasing")
    return rows


def _human_states(rows: list[dict[str, Any]], index: int) -> tuple[HumanState, ...]:
    current = rows[index]["privileged"]["human_positions"]
    if not current:
        return ()
    before_index = max(0, index - 5)
    after_index = min(len(rows) - 1, index + 5)
    before = rows[before_index]["privileged"]["human_positions"]
    after = rows[after_index]["privileged"]["human_positions"]
    duration = max(
        1.0e-6,
        float(rows[after_index]["timestamp"]) - float(rows[before_index]["timestamp"]),
    )
    states: list[HumanState] = []
    for human_index, position in enumerate(current):
        if human_index < len(before) and human_index < len(after):
            velocity = (
                (float(after[human_index][0]) - float(before[human_index][0])) / duration,
                (float(after[human_index][1]) - float(before[human_index][1])) / duration,
            )
            speed = math.hypot(*velocity)
            if speed > 2.0:
                velocity = (velocity[0] * 2.0 / speed, velocity[1] * 2.0 / speed)
        else:
            velocity = (0.0, 0.0)
        states.append(
            HumanState(
                position=(float(position[0]), float(position[1])),
                velocity=velocity,
                radius=0.35,
            )
        )
    return tuple(states)


def _local_grid(row: dict[str, Any], resolution: float = 0.1) -> OccupancyGrid:
    pose = row["robot_pose"]
    goal = row["goal"]
    path = navigation_path_or_goal(
        ((float(point[0]), float(point[1])) for point in row["global_path"]),
        (float(goal[0]), float(goal[1])),
    )
    x_values = [float(pose[0]), float(goal[0]), *(float(point[0]) for point in path)]
    y_values = [float(pose[1]), float(goal[1]), *(float(point[1]) for point in path)]
    origin_x = math.floor((min(x_values) - 2.0) / resolution) * resolution
    origin_y = math.floor((min(y_values) - 2.0) / resolution) * resolution
    width = max(20, math.ceil((max(x_values) + 2.0 - origin_x) / resolution))
    height = max(20, math.ceil((max(y_values) + 2.0 - origin_y) / resolution))
    occupied = np.zeros((height, width), dtype=np.bool_)
    scan = _observable_lidar(row).astype(np.float64)
    angles = np.linspace(-LIDAR_FOV_RADIANS / 2.0, LIDAR_FOV_RADIANS / 2.0, scan.size)
    yaw = float(pose[2])
    for distance, angle in zip(scan, angles, strict=True):
        if not math.isfinite(float(distance)) or not 0.05 <= distance <= 6.0:
            continue
        x = float(pose[0]) + float(distance) * math.cos(yaw + float(angle))
        y = float(pose[1]) + float(distance) * math.sin(yaw + float(angle))
        column = math.floor((x - origin_x) / resolution)
        grid_row = math.floor((y - origin_y) / resolution)
        if 0 <= grid_row < height and 0 <= column < width:
            occupied[grid_row, column] = True
    return OccupancyGrid(occupied, resolution, origin_x, origin_y)


def _privileged_state(
    rows: list[dict[str, Any]], index: int
) -> tuple[PrivilegedState, OccupancyGrid]:
    row = rows[index]
    pose = Pose2D(*map(float, row["robot_pose"]))
    goal = Pose2D(*map(float, row["goal"]))
    path = navigation_path_or_goal(
        ((float(point[0]), float(point[1])) for point in row["global_path"]),
        (goal.x, goal.y),
    )
    state = PrivilegedState(
        robot_pose=pose,
        robot_velocity=Velocity2D(*map(float, row["robot_velocity"])),
        original_goal=goal,
        global_path=path,
        humans=_human_states(rows, index),
        time_step=0.1,
    )
    return state, _local_grid(row)


def _selected_indices(rows: list[dict[str, Any]], stride: int, threshold: float) -> list[int]:
    if stride <= 0:
        raise ValueError("stride must be positive")
    return [
        index
        for index in range(0, len(rows), stride)
        if float(rows[index]["failure_score"]) >= threshold
        or int(rows[index]["recovery_state"]) != 0
    ]


def _observable_arrays(rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    lidar = np.stack([_observable_lidar(row) for row in rows])
    goal_polar: list[tuple[float, float]] = []
    waypoints: list[np.ndarray] = []
    progress_history: list[np.ndarray] = []
    angular_history: list[np.ndarray] = []
    distances = [float(row["distance_to_goal"]) for row in rows]
    angular = [float(row["robot_velocity"][1]) for row in rows]
    for index, row in enumerate(rows):
        pose = Pose2D(*map(float, row["robot_pose"]))
        goal = row["goal"]
        dx, dy = float(goal[0]) - pose.x, float(goal[1]) - pose.y
        local_x = math.cos(pose.yaw) * dx + math.sin(pose.yaw) * dy
        local_y = -math.sin(pose.yaw) * dx + math.cos(pose.yaw) * dy
        goal_polar.append((math.hypot(dx, dy), math.atan2(local_y, local_x)))
        path = navigation_path_or_goal(
            ((float(point[0]), float(point[1])) for point in row["global_path"]),
            (float(goal[0]), float(goal[1])),
        )
        waypoints.append(select_local_path_waypoints(path, pose))
        start = max(0, index - 9)
        distance_window = [distances[start]] * (10 - (index - start + 1)) + distances[
            start : index + 1
        ]
        angular_window = [angular[start]] * (10 - (index - start + 1)) + angular[start : index + 1]
        progress_history.append(np.asarray(distance_window, dtype=np.float32))
        angular_history.append(np.asarray(angular_window, dtype=np.float32))
    return {
        "lidar": lidar,
        "goal_polar": np.asarray(goal_polar, dtype=np.float32),
        "path_waypoints": np.asarray(waypoints, dtype=np.float32),
        "robot_velocity": np.asarray([row["robot_velocity"] for row in rows], dtype=np.float32),
        "base_action": np.asarray([row["base_cmd_vel"] for row in rows], dtype=np.float32),
        "progress_history": np.asarray(progress_history, dtype=np.float32),
        "angular_velocity_history": np.asarray(angular_history, dtype=np.float32),
        "planner_status": np.asarray([row["planner_status"] for row in rows], dtype=np.int8),
        "failure_prediction": np.asarray(
            [row["failure_prediction"] for row in rows], dtype=np.float32
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_jsonl", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "interim" / "expert_smoke.h5",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "data" / "manifests" / "expert_smoke_summary.json",
    )
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--failure-threshold", type=float, default=0.65)
    parser.add_argument("--rejoin-release-threshold", type=float, default=0.65)
    parser.add_argument("--collision-latched-action-clearance", type=float, default=0.65)
    parser.add_argument("--wait-budget-decisions", type=int, default=3)
    args = parser.parse_args()
    rows = _load(args.raw_jsonl)
    indices = _selected_indices(rows, args.stride, args.failure_threshold)
    if not indices:
        raise ValueError("episode contains no recovery-relevant states")
    actions: list[int] = []
    costs: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    margins: list[float] = []
    successes: list[bool] = []
    previous_side = 0
    repeated_waits = 0
    previous_index: int | None = None
    for index in indices:
        if (
            previous_index is None
            or float(rows[index]["timestamp"]) - float(rows[previous_index]["timestamp"]) > 1.0
        ):
            previous_side = 0
            repeated_waits = 0
        state, grid = _privileged_state(rows, index)
        mask = compute_action_mask(
            state.robot_pose,
            grid,
            replan_available=True,
        )
        scan = _observable_lidar(rows[index]).astype(np.float64)
        collision_risk = float(rows[index]["failure_prediction"][0])
        collision_latched = collision_risk >= args.rejoin_release_threshold
        mask = apply_observable_scan_mask(
            mask,
            scan,
            angle_min=-LIDAR_FOV_RADIANS / 2.0,
            angle_increment=LIDAR_FOV_RADIANS / max(1, scan.size - 1),
            swept_clearance_m=(
                args.collision_latched_action_clearance if collision_latched else 0.48
            ),
            target_clearance_m=(
                args.collision_latched_action_clearance if collision_latched else 0.25
            ),
            allow_unobserved_backup=False,
        )
        mask = apply_path_corridor_mask(mask, state.robot_pose, state.global_path)
        mask = constrain_rejoin_actions(
            mask,
            collision_risk=collision_risk,
            release_threshold=args.rejoin_release_threshold,
        )
        failure_prediction = rows[index]["failure_prediction"]
        effective_waits = failure_conditioned_wait_count(
            repeated_waits,
            wait_budget=args.wait_budget_decisions,
            freeze_score=float(failure_prediction[1]),
            deadlock_score=float(failure_prediction[3]),
            trigger_threshold=float(args.failure_threshold),
        )
        mask = constrain_stalled_wait(
            mask,
            consecutive_waits=effective_waits,
            wait_budget=args.wait_budget_decisions,
        )
        label = PlanningRecoveryExpert(grid).label(
            state,
            mask,
            previous_side=previous_side,
            repeated_waits=repeated_waits,
        )
        actions.append(label.action_id)
        costs.append(label.action_costs)
        masks.append(label.valid_mask)
        margins.append(label.margin)
        successes.append(label.predicted_success)
        previous_side, repeated_waits = update_expert_history(
            label.action_id,
            previous_side=previous_side,
            repeated_waits=repeated_waits,
        )
        previous_index = index
    observable = _observable_arrays(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(args.output, "w") as handle:
        handle.attrs["source_jsonl"] = str(args.raw_jsonl)
        handle.attrs["schema_version"] = 1
        observations = handle.create_group("observations")
        for name, values in observable.items():
            observations.create_dataset(name, data=values, compression="gzip")
        observations.create_dataset("episode_start_index", data=np.zeros(len(rows), dtype=np.int32))
        handle.create_dataset("sample_index", data=np.asarray(indices, dtype=np.int32))
        handle.create_dataset(
            "timestamp",
            data=np.asarray([rows[index]["timestamp"] for index in indices], dtype=np.float64),
        )
        labels = handle.create_group("labels")
        labels.create_dataset("expert_action", data=np.asarray(actions, dtype=np.int16))
        labels.create_dataset("expert_costs", data=np.stack(costs), compression="gzip")
        labels.create_dataset("expert_margin", data=np.asarray(margins, dtype=np.float32))
        labels.create_dataset("action_mask", data=np.stack(masks), compression="gzip")
        labels.create_dataset("predicted_success", data=np.asarray(successes, dtype=np.bool_))
    summary = {
        "source_jsonl": str(args.raw_jsonl),
        "sample_count": len(indices),
        "illegal_action_count": int(
            sum(not bool(mask[action]) for mask, action in zip(masks, actions, strict=True))
        ),
        "predicted_success_count": int(sum(successes)),
        "rejoin_release_threshold": args.rejoin_release_threshold,
        "collision_latched_action_clearance": args.collision_latched_action_clearance,
        "wait_budget_decisions": args.wait_budget_decisions,
        "finite_selected_cost_count": int(
            sum(
                math.isfinite(float(cost[action]))
                for cost, action in zip(costs, actions, strict=True)
            )
        ),
        "action_counts": {str(action): actions.count(action) for action in sorted(set(actions))},
        "margin": {
            "minimum": float(np.min(margins)),
            "median": float(np.median(margins)),
            "maximum": float(np.max(margins)),
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Expert labels: samples={len(indices)} illegal={summary['illegal_action_count']} "
        f"predicted_success={summary['predicted_success_count']}"
    )


if __name__ == "__main__":
    main()
