# Eight-family PGRR recovery-progress diagnostic

Development diagnostic only; this is not final evaluation evidence.

| Family | Outcome | Net goal progress (m) | Recovery time | Cycles | Rejoins |
|---|---:|---:|---:|---:|---:|
| diagonal_cut_in_corridor | TIMEOUT | 21.126 | 0.0% | 0 | 0 |
| occluded_side_emergence | TIMEOUT | 11.477 | 33.5% | 4 | 3 |
| recurrent_bidirectional_crossing | TIMEOUT | 8.074 | 55.7% | 8 | 7 |
| narrow_corridor_head_on_deadlock | PLANNER_FAILURE | -0.252 | 99.0% | 2 | 1 |
| closing_gap_multi_pedestrian | TIMEOUT | 7.804 | 50.8% | 6 | 5 |
| lead_pedestrian_sudden_stop | TIMEOUT | 10.214 | 38.2% | 5 | 4 |
| bottleneck_cross_flow_merge | TIMEOUT | 8.309 | 49.6% | 4 | 3 |
| goal_approach_lateral_interruption | TIMEOUT | 17.390 | 13.6% | 1 | 0 |

## Aggregate

- Raw hashes verified: True
- Episodes with positive/nonpositive net progress: 7/1
- Recovery cycles: 30
- Completed rejoins: 23
- Cycles with positive/nonpositive goal progress: 5/25
- Time-weighted recovery-state fraction: 39.2%
- Mean low-linear-speed sample fraction: 22.4%
- Trigger failure counts: {"COLLISION_RISK": 20, "NO_POSITIVE_FAILURE_SCORE": 10}
- Positive-cycle action events: {"BACKUP": 1, "CONTINUE": 9, "SUBGOAL_0": 1, "WAIT": 8}
- Nonpositive-cycle action events: {"BACKUP": 53, "CONTINUE": 45, "REPLAN": 1, "SUBGOAL_0": 2, "SUBGOAL_2": 1, "WAIT": 55}
- Trigger/progress counts: {"COLLISION_RISK|nonpositive": 18, "COLLISION_RISK|positive": 2, "NO_POSITIVE_FAILURE_SCORE|nonpositive": 7, "NO_POSITIVE_FAILURE_SCORE|positive": 3}
- Cycles with/without a learned-policy decision: 25/5
- Learned actions in positive cycles: {"CONTINUE": 1, "SUBGOAL_0": 1, "WAIT": 3}
- Learned actions in nonpositive cycles: {"BACKUP": 32, "REPLAN": 1, "SUBGOAL_0": 2, "SUBGOAL_2": 1, "WAIT": 19}
