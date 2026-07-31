#!/usr/bin/env python3
"""Compare legacy straight-line and planner-command Oracle trigger decisions."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ramp_core.observations import HumanState
from ramp_core.planning.online import (
    estimate_human_states,
    privileged_collision_risk,
    privileged_time_to_collision,
)
from ramp_core.types import Pose2D, Velocity2D


@dataclass(frozen=True, slots=True)
class TriggerSummary:
    episode_id: str
    source_policy: str
    outcome: str
    sample_count: int
    legacy_risk_frames: int
    planner_risk_frames: int
    planner_unevasive_risk_frames: int
    planner_ttc_1_0_frames: int
    planner_ttc_1_5_frames: int
    legacy_risk_events: int
    planner_risk_events: int
    planner_unevasive_risk_events: int
    planner_ttc_1_0_events: int
    planner_ttc_1_5_events: int
    legacy_max_consecutive_frames: int
    planner_max_consecutive_frames: int
    planner_unevasive_max_consecutive_frames: int
    planner_ttc_1_0_max_consecutive_frames: int
    planner_ttc_1_5_max_consecutive_frames: int
    legacy_risk_last_3s: bool
    planner_risk_last_3s: bool
    planner_unevasive_risk_last_3s: bool
    planner_ttc_1_0_last_3s: bool
    planner_ttc_1_5_last_3s: bool


def _events(values: list[bool]) -> int:
    return sum(
        value and (index == 0 or not values[index - 1]) for index, value in enumerate(values)
    )


def _maximum_run(values: list[bool]) -> int:
    maximum = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        maximum = max(maximum, current)
    return maximum


def summarize(prefix: Path) -> TriggerSummary:
    metadata = json.loads(prefix.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    outcome = json.loads(prefix.with_suffix(".outcome.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = [
        json.loads(line)
        for line in prefix.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if not rows:
        raise ValueError(f"empty episode: {prefix}")

    tracked_positions: tuple[tuple[float, float], ...] = ()
    tracked_timestamp: float | None = None
    humans: tuple[HumanState, ...] = ()
    legacy: list[bool] = []
    planned: list[bool] = []
    planned_unevasive: list[bool] = []
    planned_ttc_1_0: list[bool] = []
    planned_ttc_1_5: list[bool] = []
    for row in rows:
        timestamp = float(row["timestamp"])
        positions = tuple(
            (float(position[0]), float(position[1]))
            for position in row["privileged"]["human_positions"]
        )
        if positions and positions != tracked_positions:
            elapsed = 0.0 if tracked_timestamp is None else timestamp - tracked_timestamp
            humans = estimate_human_states(
                positions,
                tracked_positions,
                elapsed,
                radius_m=0.35,
                maximum_speed_mps=2.0,
            )
            tracked_positions = positions
            tracked_timestamp = timestamp
        pose_values = row["robot_pose"]
        pose = Pose2D(float(pose_values[0]), float(pose_values[1]), float(pose_values[2]))
        odometry = row["robot_velocity"]
        base_command = row["base_cmd_vel"]
        legacy.append(
            privileged_collision_risk(
                pose,
                Velocity2D(float(odometry[0]), 0.0),
                humans,
            )
        )
        planned_risk = privileged_collision_risk(
            pose,
            Velocity2D(float(base_command[0]), float(base_command[1])),
            humans,
        )
        planned.append(planned_risk)
        planned_unevasive.append(planned_risk and abs(float(base_command[1])) <= 0.3)
        collision_time = privileged_time_to_collision(
            pose,
            Velocity2D(float(base_command[0]), float(base_command[1])),
            humans,
        )
        planned_ttc_1_0.append(collision_time is not None and collision_time <= 1.0)
        planned_ttc_1_5.append(collision_time is not None and collision_time <= 1.5)

    terminal_time = float(rows[-1]["timestamp"])
    last_3s = [
        index for index, row in enumerate(rows) if float(row["timestamp"]) >= terminal_time - 3.0
    ]
    return TriggerSummary(
        episode_id=str(metadata["episode_id"]),
        source_policy=str(metadata["source_policy"]),
        outcome=str(outcome["outcome"]),
        sample_count=len(rows),
        legacy_risk_frames=sum(legacy),
        planner_risk_frames=sum(planned),
        planner_unevasive_risk_frames=sum(planned_unevasive),
        planner_ttc_1_0_frames=sum(planned_ttc_1_0),
        planner_ttc_1_5_frames=sum(planned_ttc_1_5),
        legacy_risk_events=_events(legacy),
        planner_risk_events=_events(planned),
        planner_unevasive_risk_events=_events(planned_unevasive),
        planner_ttc_1_0_events=_events(planned_ttc_1_0),
        planner_ttc_1_5_events=_events(planned_ttc_1_5),
        legacy_max_consecutive_frames=_maximum_run(legacy),
        planner_max_consecutive_frames=_maximum_run(planned),
        planner_unevasive_max_consecutive_frames=_maximum_run(planned_unevasive),
        planner_ttc_1_0_max_consecutive_frames=_maximum_run(planned_ttc_1_0),
        planner_ttc_1_5_max_consecutive_frames=_maximum_run(planned_ttc_1_5),
        legacy_risk_last_3s=any(legacy[index] for index in last_3s),
        planner_risk_last_3s=any(planned[index] for index in last_3s),
        planner_unevasive_risk_last_3s=any(planned_unevasive[index] for index in last_3s),
        planner_ttc_1_0_last_3s=any(planned_ttc_1_0[index] for index in last_3s),
        planner_ttc_1_5_last_3s=any(planned_ttc_1_5[index] for index in last_3s),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = {
        "description": (
            "Offline replay only: legacy uses measured linear speed with zero angular rate; "
            "planner uses recorded base planner v/omega."
        ),
        "episodes": [asdict(summarize(prefix)) for prefix in args.prefix],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
