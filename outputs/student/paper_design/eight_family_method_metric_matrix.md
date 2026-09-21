# Eight-family algorithm-scenario-metric matrix

> Scope: train-only development evidence. This table does not establish superiority, generalization, or statistical significance.

| # | Family | Target | PGRR components being probed | Primary diagnostics | Current descriptive pair |
|---:|---|---|---|---|---|
| 1 | `diagonal_cut_in_corridor` | collision_risk | failure trigger; safe action mask; WAIT/BACKUP/subgoal | triggered; time_to_first_recovery_s; minimum_clearance_m | Base=TIMEOUT; PGRR=TIMEOUT |
| 2 | `occluded_side_emergence` | collision_risk | failure trigger; safe action mask; WAIT/BACKUP/subgoal | triggered; time_to_first_recovery_s; minimum_clearance_m | Base=COLLISION; PGRR=TIMEOUT |
| 3 | `recurrent_bidirectional_crossing` | oscillation | failure trigger; direction commitment; recovery memory | recovery_cycle_count; action_switch_count; cycle_progress_m | Base=TIMEOUT; PGRR=TIMEOUT |
| 4 | `narrow_corridor_head_on_deadlock` | freeze_or_deadlock | failure trigger; WAIT/BACKUP/subgoal/REPLAN; rejoin; lateral subgoal/WAIT/BACKUP | stationary_duration_s; cycle_progress_m; goal_restore_count; deadlock_duration_s; temporary_subgoal_count | Base=COLLISION; PGRR=PLANNER_FAILURE |
| 5 | `closing_gap_multi_pedestrian` | collision_risk_or_planner_failure | failure trigger; safe action mask; WAIT/BACKUP/subgoal; planner-failure trigger; REPLAN/temporary subgoal; goal restore | triggered; time_to_first_recovery_s; minimum_clearance_m; planner_failure_count; replan_count; goal_restore_count | Base=COLLISION; PGRR=TIMEOUT |
| 6 | `lead_pedestrian_sudden_stop` | freeze | failure trigger; WAIT/BACKUP/subgoal/REPLAN; rejoin | stationary_duration_s; cycle_progress_m; goal_restore_count | Base=COLLISION; PGRR=TIMEOUT |
| 7 | `bottleneck_cross_flow_merge` | deadlock_or_timeout | failure trigger; lateral subgoal/WAIT/BACKUP; rejoin; bounded recovery | deadlock_duration_s; temporary_subgoal_count; cycle_progress_m; rapid_retrigger_count; final_goal_distance_m | Base=COLLISION; PGRR=TIMEOUT |
| 8 | `goal_approach_lateral_interruption` | oscillation_or_planner_failure | failure trigger; direction commitment; recovery memory; planner-failure trigger; REPLAN/temporary subgoal; goal restore | recovery_cycle_count; action_switch_count; cycle_progress_m; planner_failure_count; replan_count; goal_restore_count | Base=COLLISION; PGRR=TIMEOUT |

## Paper flow

1. scenario manipulation and seeded reset
2. classical planner controls normal navigation
3. failure signal triggers recovery only when needed
4. PGRR selects WAIT/BACKUP/REPLAN/CONTINUE or one of 21 temporary subgoals
5. classical planner executes the temporary goal
6. original goal is restored and navigation rejoins
7. report preserved outcome, joint-success costs, and mechanism diagnostics

## Interpretation boundary

The current eight pairs are mechanism-development observations only. Primary outcomes must be reported for every episode; time, path length, and angular jerk are compared only on joint successes. Mechanism diagnostics explain where the pipeline activates or stalls but do not prove causality.
