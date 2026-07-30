#!/usr/bin/env python3
"""Render twenty deterministic privileged-expert validation scenes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from ramp_core.action_space import ACTION_COUNT, ACTIONS
from ramp_core.observations import HumanState, PrivilegedState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.expert import PlanningRecoveryExpert
from ramp_core.planning.rollout import rollout_action
from ramp_core.types import Pose2D, Velocity2D

ROOT = Path(__file__).resolve().parents[2]


def _state(index: int) -> PrivilegedState:
    angle = -math.pi + index * (2.0 * math.pi / 20.0)
    human = HumanState(
        position=(1.4 * math.cos(angle), 1.4 * math.sin(angle)),
        velocity=(-0.15 * math.cos(angle), -0.15 * math.sin(angle)),
        radius=0.35,
    )
    return PrivilegedState(
        robot_pose=Pose2D(0.0, 0.0, 0.0),
        robot_velocity=Velocity2D(0.0, 0.0),
        original_goal=Pose2D(5.0, 0.0, 0.0),
        global_path=tuple((step * 0.1, 0.0) for step in range(51)),
        humans=(human,),
        time_step=0.1,
    )


def _render(
    output: Path,
    expert: PlanningRecoveryExpert,
    grid: OccupancyGrid,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    with PdfPages(output) as pdf:
        for index in range(20):
            state = _state(index)
            mask = np.ones(ACTION_COUNT, dtype=np.bool_)
            mask[index] = False
            label = expert.label(state, mask)
            selected_rollout = rollout_action(
                state,
                ACTIONS[label.action_id],
                grid,
                config=expert.rollout_config,
                personal_space_m=expert.cost_weights.personal_space_m,
            )
            figure, axis = plt.subplots(figsize=(7.0, 5.0))
            finite = label.action_costs[np.isfinite(label.action_costs)]
            scale = max(1.0, float(np.percentile(finite, 90)))
            for action in ACTIONS:
                if not mask[action.action_id]:
                    continue
                rollout = rollout_action(
                    state,
                    action,
                    grid,
                    config=expert.rollout_config,
                    personal_space_m=expert.cost_weights.personal_space_m,
                )
                points = np.asarray([(pose.x, pose.y) for pose in rollout.poses])
                color = plt.cm.viridis(
                    min(1.0, float(label.action_costs[action.action_id]) / scale)
                )
                axis.plot(
                    points[:, 0],
                    points[:, 1],
                    color=color,
                    alpha=0.95 if action.action_id == label.action_id else 0.25,
                    linewidth=2.8 if action.action_id == label.action_id else 0.8,
                )
            human = state.humans[0]
            times = np.linspace(0.0, expert.rollout_config.horizon_s, 31)
            human_path = np.asarray(
                [
                    (
                        human.position[0] + human.velocity[0] * time,
                        human.position[1] + human.velocity[1] * time,
                    )
                    for time in times
                ]
            )
            axis.plot(human_path[:, 0], human_path[:, 1], "r--", label="predicted human")
            axis.scatter([0.0], [0.0], marker="o", color="black", label="robot")
            axis.scatter([5.0], [0.0], marker="*", s=120, color="gold", label="goal")
            axis.set(
                xlim=(-1.8, 2.5),
                ylim=(-2.0, 2.0),
                aspect="equal",
                xlabel="x [m]",
                ylabel="y [m]",
                title=(
                    f"Scene {index:02d}: selected={label.action_id} "
                    f"margin={label.margin:.3f} collision={selected_rollout.collision}"
                ),
            )
            axis.grid(alpha=0.25)
            axis.legend(loc="upper right", fontsize=8)
            figure.tight_layout()
            pdf.savefig(figure)
            plt.close(figure)
            records.append(
                {
                    "scene_id": index,
                    "masked_action": index,
                    "selected_action": label.action_id,
                    "best_cost": label.best_cost,
                    "second_best_cost": label.second_best_cost,
                    "margin": label.margin,
                    "selected_collision": selected_rollout.collision,
                    "predicted_success": label.predicted_success,
                }
            )
    return {
        "scene_count": len(records),
        "illegal_action_count": sum(
            int(record["selected_action"] == record["masked_action"]) for record in records
        ),
        "selected_collision_count": sum(
            int(bool(record["selected_collision"])) for record in records
        ),
        "predicted_success_count": sum(
            int(bool(record["predicted_success"])) for record in records
        ),
        "scenes": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--figure",
        type=Path,
        default=ROOT / "outputs" / "figures" / "expert_validation_synthetic.pdf",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs" / "smoke" / "expert_validation.json",
    )
    args = parser.parse_args()
    args.figure.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    grid = OccupancyGrid(np.zeros((120, 120), dtype=np.bool_), 0.1, -3.0, -3.0)
    summary = _render(args.figure, PlanningRecoveryExpert(grid), grid)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Expert validation: scenes={summary['scene_count']} "
        f"illegal={summary['illegal_action_count']} "
        f"selected_collisions={summary['selected_collision_count']}"
    )


if __name__ == "__main__":
    main()
