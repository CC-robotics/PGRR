# Eight-family telemetry coverage audit

> Design audit only. It does not establish runtime success, superiority, generalization, or significance.

| Metric | Group | Status | Families | Source fields / remaining decision |
|---|---|---|---:|---|
| `COLLISION` | primary | **direct** | 8 | outcome |
| `GOAL_REACHED` | primary | **direct** | 8 | outcome |
| `TIMEOUT` | primary | **direct** | 8 | outcome |
| `action_switch_count` | mechanism | **derivable** | 2 | recovery_action |
| `angular_jerk` | joint_success_cost | **derivable** | 8 | timestamp, robot_velocity[1] |
| `completion_time_s` | joint_success_cost | **derivable** | 8 | timestamp |
| `cycle_progress_m` | mechanism | **derivable** | 5 | goal, robot_pose, recovery_state |
| `deadlock_duration_s` | mechanism | **definition_required** | 2 | timestamp, robot_velocity, distance_to_goal, recovery_state; DECIDE: define speed, progress-window, hazard, and minimum-duration conditions |
| `final_goal_distance_m` | mechanism | **direct_and_derivable** | 1 | localized_goal_distance_m, physical_goal_distance_m, goal, robot_pose |
| `goal_restore_count` | mechanism | **derivable** | 4 | recovery_reason |
| `minimum_clearance_m` | mechanism | **definition_required** | 3 | nearest_obstacle_distance, privileged.nearest_human_distance; DECIDE: define clearance as obstacle clearance, human clearance, or report both |
| `path_length_m` | joint_success_cost | **derivable** | 8 | robot_pose, privileged.robot_pose |
| `planner_failure_count` | mechanism | **derivable** | 2 | planner_status, outcome |
| `rapid_retrigger_count` | mechanism | **derivable** | 1 | timestamp, recovery_state; preregister: preregistered rapid-retrigger window |
| `recovery_cycle_count` | mechanism | **derivable** | 2 | recovery_state |
| `replan_count` | mechanism | **derivable** | 2 | recovery_action |
| `stationary_duration_s` | mechanism | **derivable** | 2 | timestamp, robot_velocity[0]; preregister: stationary linear-speed threshold |
| `temporary_subgoal_count` | mechanism | **derivable** | 2 | recovery_action |
| `time_to_first_recovery_s` | mechanism | **derivable** | 3 | timestamp, recovery_state |
| `triggered` | mechanism | **derivable** | 3 | recovery_state, recovery_action, recovery_reason |

## Result

The matrix requests 20 unique metrics. Two still require an operational definition: deadlock_duration_s, minimum_clearance_m. All other requested metrics are directly logged or derivable from the current schema. Derivable does not mean already computed for every future run; raw artifacts must still be preserved.
