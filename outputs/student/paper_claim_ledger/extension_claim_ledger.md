# Extension evidence-to-claim ledger

> Generated from checked-in development CSV/JSON; not a held-out result.

## development_pair_outcomes

- Allowed: In eight train-only development pairs, Base collided in six; PGRR collided in none but also reached no goals.
- Forbidden inference: superiority, generalization, or statistical significance
- Source: `outputs/student/eight_family_pilot/minimal_pair_summary.csv`
- Generated numbers: `{"base_outcomes": {"COLLISION": 6, "TIMEOUT": 2}, "pair_count": 8, "pgrr_outcomes": {"PLANNER_FAILURE": 1, "TIMEOUT": 7}}`

## recovery_cycle_contract_probe

- Allowed: The explicit train-only progress contract found task progress in zero of 30 recovery cycles; this diagnoses the prototype, not causality.
- Forbidden inference: runtime threshold choice or causal attribution
- Source: `outputs/student/eight_family_pilot/recovery_contract_probe.json`
- Generated numbers: `{"cycle_count": 30, "hazard_cleared_count": 28, "maximum_cycle_progress_m": 0.169412, "meaningful_task_progress_count": 0, "median_cycle_progress_m": -0.439889, "original_goal_active_count": 30, "rapid_retrigger_count": 14, "raw_hashes_verified": true, "retrigger_observation_complete_count": 23, "verdict_counts": {"HAZARD_NOT_CLEARED": 2, "INSUFFICIENT_TASK_PROGRESS": 28}}`

## upstream_mask_trace

- Allowed: Across three selector-positive development episodes, including one validation episode, 350 decisions had complete layer traces; this establishes selector-layer replication across splits for the diagnostic path, not navigation success.
- Forbidden inference: mask causality, performance benefit, or threshold tuning
- Source: `outputs/student/eight_family_pilot/mask_trace_replication_summary.json`
- Generated numbers: `{"episode_count": 6, "first_temporary_empty_stage_counts": {"map_connectivity": 0, "none": 15, "observable_scan": 306, "path_corridor": 29}, "traced_decision_count": 350, "validation_layer_replication_established": true}`

## validation_trigger_paths

- Allowed: The audited validation samples include a detector-negative diagonal case and an emergency-only head-on case; neither supplies a selector-layer trace.
- Forbidden inference: all validation episodes stayed NORMAL or detector failure
- Source: `outputs/student/eight_family_pilot/trigger_coverage_audit_20260912.json`
- Generated numbers: `{"diagnosis_counts": {"emergency_stop_only": 1, "no_recorded_failure_signal": 2, "selector_recovery_triggered": 2}}`

## next_validation_candidate

- Allowed: The preflighted non-frozen lead-stop validation episode ran to a preserved TIMEOUT and produced 191 complete selector-layer traces.
- Forbidden inference: navigation success, performance superiority, or held-out test result
- Source: `outputs/student/eight_family_pilot/mask_trace_leadstop_validation_runtime_validation.json`
- Generated numbers: `{"complete_trace_row_count": 191, "outcome": "TIMEOUT", "ready": true, "seed": 93500, "telemetry_row_count": 898, "timeout_s": 90}`

## validation_timeout_diagnostic

- Allowed: In one non-frozen validation development episode, 4 of 4 recovery cycles ended no closer to the original goal; 172 selector rows used the directional-yield WAIT/BACKUP restriction.
- Forbidden inference: that BACKUP, directional yield, or any mask caused the TIMEOUT
- Source: `outputs/student/eight_family_pilot/leadstop_validation_timeout_diagnosis.json`
- Generated numbers: `{"cycle_summary": {"cycle_count": 4, "nonpositive_progress_cycle_count": 4, "positive_progress_cycle_count": 0, "total_cycle_progress_m": -1.5116682052612305}, "goal_distance": {"at_first_failure_m": 12.114191055297852, "final_m": 11.68445110321045, "initial_m": 22.0, "minimum_m": 11.676814079284668, "progress_after_first_failure_m": 0.42973995208740234, "progress_before_first_failure_m": 9.885808944702148}, "path_length": {"after_first_failure_m": 5.931329463946754, "before_first_failure_m": 9.900290678289732}, "trace_constraint_summary": {"action_counts": {"BACKUP": 141, "REPLAN": 19, "WAIT": 31}, "confidence_max": 1.0, "confidence_min": 0.644, "directional_yield_action_counts": {"BACKUP": 141, "WAIT": 31}, "directional_yield_active_row_count": 172, "final_wait_backup_only_row_count": 172, "non_directional_yield_action_counts": {"REPLAN": 19}, "path_stage_temporary_survivor_row_count": 15, "path_survivor_action_counts": {"REPLAN": 15}, "path_survivors_removed_downstream_count": 0, "path_survivors_retained_final_count": 15, "temporary_subgoal_selected_count": 0, "traced_row_count": 191}}`

## Globally forbidden claims

- The eight-family extension establishes PGRR superiority.
- The mask trace proves the action mask causes failure.
- The validation TIMEOUT is a navigation success.
- Directional yield or BACKUP is proven to cause the validation TIMEOUT.
- Development train/validation evidence is a held-out test result.
