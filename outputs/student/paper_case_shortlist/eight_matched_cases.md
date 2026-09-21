# Eight matched qualitative case candidates

The frozen 600-episode result contains 26 matched conditions where Base did not reach and PGRR reached, spanning 5 of 8 families.
The eight rows below are a deterministic, post-hoc qualitative subset; they are not eight independent statistical claims.

| # | Family | Density | Rep | Seed | Base | Standard | Heuristic | Uniform BC | PGRR | Other failures |
|---:|---|---|---:|---:|---|---|---|---|---|---:|
| 1 | `blind_corner` | medium | 4 | 87314 | COLLISION | COLLISION | PLANNER_FAILURE | PLANNER_FAILURE | GOAL_REACHED | 3 |
| 2 | `crossing_flow` | medium | 2 | 87212 | COLLISION | COLLISION | COLLISION | GOAL_REACHED | GOAL_REACHED | 2 |
| 3 | `doorway_bottleneck` | low | 0 | 87100 | COLLISION | COLLISION | GOAL_REACHED | GOAL_REACHED | GOAL_REACHED | 1 |
| 4 | `head_on_corridor` | high | 3 | 87023 | COLLISION | COLLISION | PLANNER_FAILURE | GOAL_REACHED | GOAL_REACHED | 2 |
| 5 | `temporary_blockage` | high | 0 | 87720 | COLLISION | COLLISION | GOAL_REACHED | TIMEOUT | GOAL_REACHED | 2 |
| 6 | `blind_corner` | high | 0 | 87320 | COLLISION | COLLISION | TIMEOUT | GOAL_REACHED | GOAL_REACHED | 2 |
| 7 | `head_on_corridor` | high | 4 | 87024 | COLLISION | COLLISION | PLANNER_FAILURE | GOAL_REACHED | GOAL_REACHED | 2 |
| 8 | `temporary_blockage` | high | 1 | 87721 | COLLISION | COLLISION | PLANNER_FAILURE | GOAL_REACHED | GOAL_REACHED | 2 |

Selection rule: require Base != GOAL_REACHED and PGRR = GOAL_REACHED; choose one per eligible family, then fill to eight by other-comparator failure count and difficulty, with at most two per family when possible.

Boundary: this table may illustrate trajectories or failure mechanisms. Formal claims must continue to use all 120 paired conditions and the existing corrected statistics.
