# Two-anchor observable-scan geometry audit

## Boundary

Logged pre/post removals are exact. Predicate decomposition is an approximate replay from 180-beam resampled telemetry, not the original runtime LaserScan.

## Exact logged findings

- Decisions: 162
- Collision-latched decisions: 69
- Decisions with no temporary subgoal after observable scan: 123
- Decisions exposing forward-clearance telemetry: 133
- Empty despite logged forward clearance >= 1.5 m: 14
- Empty/non-empty by collision latch: `{"latched:decisions": 69, "latched:empty": 69, "not_latched:decisions": 93, "not_latched:empty": 54}`
- Retained-mask patterns: `{"0,1,2,6": 20, "2,9": 19, "none": 123}`
- Radius totals: `{"0.6m": {"considered": 1134, "removed": 1035, "retained": 99}, "1.0m": {"considered": 1134, "removed": 1115, "retained": 19}, "1.4m": {"considered": 1134, "removed": 1134, "retained": 0}}`
- Angle totals: `{"+0deg": {"considered": 486, "removed": 486, "retained": 0}, "+30deg": {"considered": 486, "removed": 486, "retained": 0}, "+60deg": {"considered": 486, "removed": 486, "retained": 0}, "+90deg": {"considered": 486, "removed": 466, "retained": 20}, "-30deg": {"considered": 486, "removed": 428, "retained": 58}, "-60deg": {"considered": 486, "removed": 466, "retained": 20}, "-90deg": {"considered": 486, "removed": 466, "retained": 20}}`

| action (radius, angle) | considered | retained | removed |
|---|---:|---:|---:|
| r0.6_a+0 | 162 | 0 | 162 |
| r0.6_a+30 | 162 | 0 | 162 |
| r0.6_a+60 | 162 | 0 | 162 |
| r0.6_a+90 | 162 | 20 | 142 |
| r0.6_a-30 | 162 | 39 | 123 |
| r0.6_a-60 | 162 | 20 | 142 |
| r0.6_a-90 | 162 | 20 | 142 |
| r1.0_a+0 | 162 | 0 | 162 |
| r1.0_a+30 | 162 | 0 | 162 |
| r1.0_a+60 | 162 | 0 | 162 |
| r1.0_a+90 | 162 | 0 | 162 |
| r1.0_a-30 | 162 | 19 | 143 |
| r1.0_a-60 | 162 | 0 | 162 |
| r1.0_a-90 | 162 | 0 | 162 |
| r1.4_a+0 | 162 | 0 | 162 |
| r1.4_a+30 | 162 | 0 | 162 |
| r1.4_a+60 | 162 | 0 | 162 |
| r1.4_a+90 | 162 | 0 | 162 |
| r1.4_a-30 | 162 | 0 | 162 |
| r1.4_a-60 | 162 | 0 | 162 |
| r1.4_a-90 | 162 | 0 | 162 |

## Approximate predicate replay

- Exact whole-decision match rate: 0.451
- Per-action classification match rate: 0.842
- Predicate counts: `{"approx_both_failed": 2115, "approx_both_passed": 639, "approx_capsule_only_failed": 648}`

The approximation is useful only if its reported agreement is adequate. It must not be
used to relax a safety clearance, retrain a model, or claim causal failure without a new
runtime trace that records the original scan or the two predicate outcomes directly.
