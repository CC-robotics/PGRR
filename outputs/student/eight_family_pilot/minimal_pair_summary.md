# Eight-family minimal Base/PGRR development pilot

> Development evidence only. Train scenarios; no held-out test, tuning, or superiority claim.

| # | Family | Base | Collision type | PGRR | Base dist. | PGRR dist. | Triggered | Decisions | Subgoals | Restores |
|---:|---|---|---|---|---:|---:|---|---:|---:|---:|
| 1 | diagonal_cut_in_corridor | TIMEOUT | none | TIMEOUT | 0.692 | 0.865 | false | 1 | 0 | 0 |
| 2 | occluded_side_emergence | COLLISION | static_geometry | TIMEOUT | 9.991 | 10.507 | true | 27 | 0 | 3 |
| 3 | recurrent_bidirectional_crossing | TIMEOUT | none | TIMEOUT | 1.319 | 13.908 | true | 56 | 1 | 4 |
| 4 | narrow_corridor_head_on_deadlock | COLLISION | dynamic_actor | PLANNER_FAILURE | 16.908 | 22.252 | true | 34 | 0 | 0 |
| 5 | closing_gap_multi_pedestrian | COLLISION | dynamic_actor | TIMEOUT | 13.070 | 14.196 | true | 41 | 0 | 5 |
| 6 | lead_pedestrian_sudden_stop | COLLISION | dynamic_actor | TIMEOUT | 11.570 | 11.791 | true | 28 | 1 | 4 |
| 7 | bottleneck_cross_flow_merge | COLLISION | dynamic_actor | TIMEOUT | 12.438 | 13.684 | true | 38 | 2 | 3 |
| 8 | goal_approach_lateral_interruption | COLLISION | dynamic_actor | TIMEOUT | 3.630 | 4.610 | true | 10 | 0 | 0 |

## Aggregate diagnostic

- Complete pairs: 8/8.
- Base outcomes: {'COLLISION': 6, 'TIMEOUT': 2}.
- PGRR outcomes: {'PLANNER_FAILURE': 1, 'TIMEOUT': 7}.
- Base collisions: 5 dynamic actor, 1 static geometry.
- PGRR recovery triggered in 7/8 pairs.
- PGRR decisions: 235; temporary subgoals: 4; original-goal restores: 19.
- Goal reaches across both methods: 0.
- Preserved infrastructure attempts: 2.

The pilot exposes a safety/completion tradeoff: PGRR had no collision in the six pairs where Base collided, but it did not reach the goal in any pair. The comparator phase must remain paused because the minimal-pair health criterion was not met.
