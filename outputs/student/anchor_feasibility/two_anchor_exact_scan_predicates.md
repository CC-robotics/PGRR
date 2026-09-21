# Exact original-scan predicate summary

## Boundary

exact original-scan predicate telemetry; two train-only anchors. This is mechanism evidence, not a performance comparison.

## Aggregate

- Exact mask equivalence: 192/192
- Empty scan-layer outputs: 122/192
- Empty/non-empty causes: `{"capsule_has_no_entering_action": 122, "nonempty_intersection": 70}`
- Per-action predicate outcomes: `{"both_failed": 3161, "capsule_only_failed": 556, "passed_both": 315}`
- Active clearance pairs: `{"target=0.250,swept=0.480": 39, "target=0.900,swept=0.900": 153}`

| action | considered | direction pass | capsule pass | both/output pass |
|---|---:|---:|---:|---:|
| r0.6_a+0 | 192 | 78 | 35 | 35 |
| r0.6_a+30 | 192 | 149 | 20 | 20 |
| r0.6_a+60 | 192 | 35 | 20 | 20 |
| r0.6_a+90 | 192 | 24 | 20 | 20 |
| r0.6_a-30 | 192 | 63 | 55 | 55 |
| r0.6_a-60 | 192 | 154 | 55 | 55 |
| r0.6_a-90 | 192 | 55 | 55 | 55 |
| r1.0_a+0 | 192 | 58 | 0 | 0 |
| r1.0_a+30 | 192 | 30 | 0 | 0 |
| r1.0_a+60 | 192 | 20 | 0 | 0 |
| r1.0_a+90 | 192 | 24 | 0 | 0 |
| r1.0_a-30 | 192 | 59 | 55 | 55 |
| r1.0_a-60 | 192 | 20 | 0 | 0 |
| r1.0_a-90 | 192 | 20 | 0 | 0 |
| r1.4_a+0 | 192 | 43 | 0 | 0 |
| r1.4_a+30 | 192 | 15 | 0 | 0 |
| r1.4_a+60 | 192 | 0 | 0 | 0 |
| r1.4_a+90 | 192 | 4 | 0 | 0 |
| r1.4_a-30 | 192 | 20 | 0 | 0 |
| r1.4_a-60 | 192 | 0 | 0 | 0 |
| r1.4_a-90 | 192 | 0 | 0 | 0 |

No threshold or policy was changed. Any candidate correction must be designed on
train/validation evidence and must preserve the collision-safety boundary.
