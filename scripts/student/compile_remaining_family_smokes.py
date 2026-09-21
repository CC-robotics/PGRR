"""Generate family 7/8 training prototypes through the shared artifact writer."""

from __future__ import annotations

import json
import math
from pathlib import Path

from eight_family_common import ROOT, base_compiler, load_draft, write_smoke


def actor(base, index, start, end, speed, cyclic):
    yaw = math.atan2(end[1] - start[1], end[0] - start[0])
    start, end = [*start, yaw], [*end, yaw]
    behavior = base._behavior()
    behavior["once"] = not cyclic
    return dict(
        name=f"ped_{index:02d}",
        id=index + 1,
        pos=start,
        type="adult",
        model="gazebo_actor",
        waypoints=[start, end],
        max_vel=speed,
        radius=0.35,
        robot_avoidance_distance_m=0.8,
        cyclic_goals=cyclic,
        goal_radius=0.3,
        behavior=behavior,
    )


def build(config, family_id):
    base = base_compiler()
    family = next(f for f in config["families"] if f["id"] == family_id)
    p = family["prototype"]
    g = config["prototype_geometry"]
    static = []
    for side, y in [("south", 10.55), ("north", 13.45)]:
        static += base._shelves_line((4.0, y), (28.0, y), prefix=side)
    if family_id == "bottleneck_cross_flow_merge":
        # Width denotes clear space after the occupancy model's 0.45 m shelf half-width.
        half = p["bottleneck_width_m"] / 2 + 0.45
        x0, x1 = p["bottleneck_x_range_m"]
        for side, y in [("lower", 12 - half), ("upper", 12 + half)]:
            static += base._shelves_line((x0, y), (x1, y), prefix="throat_" + side)
        actors = [
            actor(
                base, i, (x, 11.5 if i == 0 else 12.5), (x, 12.5 if i == 0 else 11.5), speed, True
            )
            for i, (x, speed) in enumerate(
                zip(p["cross_flow_x_m"], p["cross_flow_speed_mps"], strict=True)
            )
        ]
        density, seed = "medium", 91610
        limitations = ["cross_flow_rate and merge_phase not independently controlled"]
    elif family_id == "goal_approach_lateral_interruption":
        # A cyclic route keeps the crossing active when the robot arrives.
        # Exact event-triggered timing and physical occlusion require runtime work.
        x = p["goal_approach_x_m"][1]
        actors = [actor(base, 0, (x, 11.1), (x, 12.9), p["pedestrian_speed_mps"][0], True)]
        density, seed = "low", 91700
        limitations = [
            "cyclic spatial prototype; not a timed one-shot interruption",
            "occlusion not implemented in this prototype",
        ]
    else:
        raise ValueError("only families 7 and 8 are implemented here")
    scenario_id = f"{family_id}_{density}_train_r00_s{seed}"
    return dict(
        ramp_metadata=dict(
            schema_version=1,
            benchmark_id=config["benchmark_id"],
            scenario_id=scenario_id,
            family=family_id,
            density=density,
            split="train",
            seed=seed,
            replicate=0,
            map_id=config["map"]["id"],
            prototype_status="geometry_only_runtime_pending",
            limitations=limitations,
        ),
        robots=[dict(start=g["robot_start"], goal=g["robot_goal"])],
        obstacles=dict(static=static, interactive=[], dynamic=actors),
    )


def compile_all(output_root: Path):
    config = load_draft(ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml")
    records = []
    for family in ["bottleneck_cross_flow_merge", "goal_approach_lateral_interruption"]:
        records.append(write_smoke(config, build(config, family), output_root, family))
    manifest = output_root / "families_7_8_manifest.json"
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    print(json.dumps(compile_all(ROOT / "outputs/student/families_7_8_smoke"), indent=2))
