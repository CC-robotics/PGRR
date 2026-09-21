# Eight-family core-readiness triage

## Boundary

eight single train-only development pairs; no held-out claims.

## Aggregate

- Scenario hashes verified: 8/8
- Base challenging: 8/8
- PGRR trigger observed: 7/8
- Named-event semantics complete: 2/8
- PGRR goal reached: 0/8
- Core comparative ready: 0/8

## Family triage

| Family | Base | PGRR | Trigger | Semantics | Next gate |
|---|---|---|---:|---:|---|
| `diagonal_cut_in_corridor` | TIMEOUT | TIMEOUT | False | True | `trigger_or_scenario_activation_audit` |
| `occluded_side_emergence` | COLLISION | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |
| `recurrent_bidirectional_crossing` | TIMEOUT | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |
| `narrow_corridor_head_on_deadlock` | COLLISION | PLANNER_FAILURE | True | True | `recovery_progress_and_candidate_availability` |
| `closing_gap_multi_pedestrian` | COLLISION | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |
| `lead_pedestrian_sudden_stop` | COLLISION | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |
| `bottleneck_cross_flow_merge` | COLLISION | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |
| `goal_approach_lateral_interruption` | COLLISION | TIMEOUT | True | False | `event_semantics_and_task_feasibility` |

## Decision

preserve all eight as development stress diagnostics; do not expand repeats yet. Repair semantic/activation gates and require train then validation goal-reaching before promoting a family into the core comparative set.

No current family is discarded, and no current family is yet promoted as proof that
PGRR succeeds where Base fails. This prevents multiplying repeats on structurally
unhealthy prototypes while retaining every completed run as diagnostic evidence.
