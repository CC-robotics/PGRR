# Two-anchor scenario-semantic audit

## Boundary

static schema and geometry audit; no simulator counterfactual.

## Findings

### lead_pedestrian_sudden_stop

- Scenario: `lead_pedestrian_sudden_stop_low_train_r00_s91500`
- Prototype status: `draft_geometry_not_frozen`
- Cyclic actor: `False`
- Actor route length: 6.000 m
- Actor endpoint to robot goal: 11.000 m
- Semantic checks: `{"explicit_stop_duration": false, "explicit_stop_time_or_trigger": false, "terminal_endpoint_on_robot_path": true, "terminal_stop_may_persist_on_route": true}`
- Interpretation: The file encodes a lead actor that ends on the robot centerline, but not an independently timed sudden-stop event or a bounded release. Treat it as a persistent-blockage stress prototype until event timing is implemented.

### goal_approach_lateral_interruption

- Scenario: `goal_approach_lateral_interruption_low_train_r00_s91700`
- Prototype status: `geometry_only_runtime_pending`
- Cyclic actor: `True`
- Actor route length: 1.800 m
- Actor endpoint to robot goal: 3.132 m
- Semantic checks: `{"explicit_robot_approach_trigger": false, "occlusion_implemented": false, "one_shot_interruption": false, "route_crosses_robot_path": true}`
- Interpretation: The file encodes a cyclic crossing near the goal, not an approach-triggered one-shot interruption; its own metadata also says occlusion is absent. Treat it as a spatial crossing stress prototype, not the named causal event.

## Recommendation

retain both artifacts as stress prototypes and historical diagnostics; build event-controlled train/validation variants before algorithm changes or core claims.

These files remain useful as stress tests and provenance. They should not be
discarded or silently replaced, and they should not drive a safety-threshold change.
