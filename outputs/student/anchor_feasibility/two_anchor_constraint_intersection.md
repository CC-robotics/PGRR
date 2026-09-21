# Anchor constraint-intersection audit

## Boundary

exact logged mask intersections from two train-only anchors. This is not a counterfactual threshold ablation.

## Results

- Decisions: 89
- Scan-empty decisions: 55
- Scan-nonempty decisions: 34
- Final temporary-empty decisions: 89
- First empty constraint: `{"bc_yield_mask": 34, "observable_scan": 55}`
- Scan survivor occurrences: `{"2": 34}`
- Downstream removals: `{"bc_yield_mask": {"2": 34}}`
- Temporary actions actually selected: 0

The learned selector never received a temporary subgoal in these decisions. The
scan-safe residual is a 0.6 m, -30 degree candidate, and the active directional-yield
constraint removes it. Diagnose candidate/constraint compatibility and scenario
feasibility before changing a safety threshold or retraining the policy.
