# Final Failure Analysis

This report is generated from the locked final result table only. It describes terminal outcomes and recorded telemetry; it does not infer causal mechanisms that are absent from those artifacts.

## Provenance and scope

- Source: `outputs/final/results.parquet`
- Source SHA-256: `b8a60bf442ab7add77d7565bdfb0c1fecb3904070dab82f6350d2c5aa30362fc`
- Project commit recorded by all rows: `35d7e601cd6f5baf168948a7174cd32fa9c37c5b`
- Manifest result rows: 64
- Algorithm episodes: 64
- Excluded terminal rows: 0
- Excluded physical attempts retained by the runner: 3

## Classification policy

- `collision_human` and `collision_static` require an explicit contact type in   `outcome_detail`. A generic LiDAR or collision message remains   `collision_unattributed`.
- `timeout_stagnation` means less than 0.150 m net   goal-distance progress in the final 4.0 s, computed from the   stored timeline. It is a kinematic observation, not a diagnosis of why progress   stopped.
- `planner_abort` is assigned only to the terminal `PLANNER_FAILURE` outcome.
- Simulator failures and invalid resets are shown separately and remain excluded   from algorithm metrics.

## Category totals

| Category | Count | Metric scope |
|---|---:|---|
| Human collision | 22 | algorithm |
| Static-geometry collision | 4 | algorithm |
| Collision, contact type unresolved | 0 | algorithm |
| Timeout / terminal stagnation | 16 | algorithm |
| Timeout with terminal progress | 7 | algorithm |
| Timeout, terminal progress unavailable | 0 | algorithm |
| Planner abort | 0 | algorithm |
| Simulator failure (excluded) | 0 | excluded technical outcome |
| Invalid reset (excluded) | 0 | excluded technical outcome |

## Counts by method, scenario family, and density

Only observed non-success categories are listed; zero-count categories remain visible in the totals above.

| Category | Method | Family | Density | Episodes |
|---|---|---|---|---:|
| Human collision | base | doorway_bottleneck | low | 1 |
| Human collision | base | doorway_bottleneck | medium | 1 |
| Human collision | base | doorway_bottleneck | high | 1 |
| Human collision | base | group_blocking | low | 1 |
| Human collision | base | group_blocking | medium | 1 |
| Human collision | base | group_blocking | high | 1 |
| Human collision | base | head_on_corridor | low | 1 |
| Human collision | base | head_on_corridor | medium | 1 |
| Human collision | base | head_on_corridor | high | 1 |
| Human collision | base | opposite_streams | low | 1 |
| Human collision | base | opposite_streams | medium | 1 |
| Human collision | base | opposite_streams | high | 1 |
| Human collision | base | overtaking | low | 1 |
| Human collision | base | overtaking | medium | 1 |
| Human collision | base | overtaking | high | 1 |
| Human collision | base | temporary_blockage | high | 1 |
| Human collision | standard | doorway_bottleneck | high | 1 |
| Human collision | standard | group_blocking | high | 1 |
| Human collision | standard | head_on_corridor | high | 1 |
| Human collision | standard | opposite_streams | high | 1 |
| Human collision | standard | overtaking | high | 1 |
| Human collision | standard | temporary_blockage | high | 1 |
| Static-geometry collision | base | blind_corner | low | 1 |
| Static-geometry collision | base | blind_corner | medium | 1 |
| Static-geometry collision | base | blind_corner | high | 1 |
| Static-geometry collision | standard | blind_corner | high | 1 |
| Timeout / terminal stagnation | bc | doorway_bottleneck | low | 1 |
| Timeout / terminal stagnation | bc | doorway_bottleneck | medium | 1 |
| Timeout / terminal stagnation | bc | doorway_bottleneck | high | 1 |
| Timeout / terminal stagnation | bc | head_on_corridor | low | 1 |
| Timeout / terminal stagnation | bc | head_on_corridor | medium | 1 |
| Timeout / terminal stagnation | bc | head_on_corridor | high | 1 |
| Timeout / terminal stagnation | bc | opposite_streams | low | 1 |
| Timeout / terminal stagnation | bc | opposite_streams | medium | 1 |
| Timeout / terminal stagnation | bc | overtaking | high | 1 |
| Timeout / terminal stagnation | heuristic | blind_corner | high | 1 |
| Timeout / terminal stagnation | heuristic | crossing_flow | high | 1 |
| Timeout / terminal stagnation | heuristic | doorway_bottleneck | high | 1 |
| Timeout / terminal stagnation | heuristic | head_on_corridor | high | 1 |
| Timeout / terminal stagnation | heuristic | opposite_streams | high | 1 |
| Timeout / terminal stagnation | heuristic | overtaking | high | 1 |
| Timeout / terminal stagnation | heuristic | temporary_blockage | high | 1 |
| Timeout with terminal progress | bc | blind_corner | low | 1 |
| Timeout with terminal progress | bc | blind_corner | medium | 1 |
| Timeout with terminal progress | bc | blind_corner | high | 1 |
| Timeout with terminal progress | bc | opposite_streams | high | 1 |
| Timeout with terminal progress | bc | overtaking | low | 1 |
| Timeout with terminal progress | bc | overtaking | medium | 1 |
| Timeout with terminal progress | bc | temporary_blockage | high | 1 |

## Recorded recovery behavior

The trigger and intervention columns below are descriptive aggregates from the final table. They are not used to attribute an outcome to the recovery policy.

| Method | Episodes | Non-success outcomes | Trigger count | Trigger mean | Recovery-timeline episodes | Intervention ratio mean | Non-CONTINUE samples | WAIT samples | BACKUP samples |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 24 | 19 | 0 | 0.000 | 0 | 0.040 | 0 | not recorded | not recorded |
| bc | 24 | 16 | 125 | 5.208 | 22 | 0.619 | 23042 | not recorded | not recorded |
| heuristic | 8 | 7 | 49 | 6.125 | 8 | 0.757 | 9812 | not recorded | not recorded |
| standard | 8 | 7 | 0 | 0.000 | 0 | 0.050 | 0 | not recorded | not recorded |

Action-specific counts for WAIT, BACKUP are not present in `results.parquet`; this report does not infer them from recovery state, terminal outcome, or free-text detail.

## Deterministic representative episodes

For each category, at most three rows are selected by a fixed method/family/density/episode ordering with method and family coverage preferred. The listed raw files are SHA-256 verified against the final result table.

### Human collision

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `doorway_bottleneck_low_test_s03100_eval_base_a0_dwb` | base | doorway_bottleneck | low | explicit outcome detail: privileged robot-human overlap | `data/raw/doorway_bottleneck_low_test_s03100_eval_base_a0_dwb.jsonl` | `3b5f70c08239c27f7e16c6c7bba39b6d6ccdcfbb66333d9f096fe4c81eb4aa04` |
| `doorway_bottleneck_high_test_s03120_eval_standard_a0_dwb` | standard | doorway_bottleneck | high | explicit outcome detail: privileged robot-human overlap | `data/raw/doorway_bottleneck_high_test_s03120_eval_standard_a0_dwb.jsonl` | `fa17c2c58c30ad38c3ca139608ab02fef3bd74409fefbe606947cbb164515e3d` |
| `group_blocking_low_test_s03400_eval_base_a0_dwb` | base | group_blocking | low | explicit outcome detail: privileged robot-human overlap | `data/raw/group_blocking_low_test_s03400_eval_base_a0_dwb.jsonl` | `19dbe567132629b13043f3fa962c21ecb993c979b0e6c3e7179f90bdadcffbcd` |

### Static-geometry collision

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_low_test_s03300_eval_base_a0_dwb` | base | blind_corner | low | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_low_test_s03300_eval_base_a0_dwb.jsonl` | `00a4ae59854ed16cd7063c7687d64980e2bf6a06d54f88effb466dfc4d68ac4d` |
| `blind_corner_high_test_s03320_eval_standard_a0_dwb` | standard | blind_corner | high | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_high_test_s03320_eval_standard_a0_dwb.jsonl` | `0d9107a086e2fa8dd30ac4795993dfcbd9e46535c0bfebf1c9bc678be4468ea2` |
| `blind_corner_medium_test_s03310_eval_base_a0_dwb` | base | blind_corner | medium | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_medium_test_s03310_eval_base_a0_dwb.jsonl` | `6576bfee3f38efa0f5293fa5cac02d4435472556bf32e4be65a0f9ec540258d0` |

### Collision, contact type unresolved

No final episode was assigned to this category.

### Timeout / terminal stagnation

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `doorway_bottleneck_low_test_s03100_eval_bc_a0_dwb` | bc | doorway_bottleneck | low | timeout; terminal 4.0 s net goal progress -0.093 m < 0.150 m | `data/raw/doorway_bottleneck_low_test_s03100_eval_bc_a0_dwb.jsonl` | `74024e374896e80fc4cf5671a0a5984ef5d542970fe84353d0b26669e632c8d4` |
| `blind_corner_high_test_s03320_eval_heuristic_a0_dwb` | heuristic | blind_corner | high | timeout; terminal 4.0 s net goal progress -0.190 m < 0.150 m | `data/raw/blind_corner_high_test_s03320_eval_heuristic_a0_dwb.jsonl` | `21c1aba5c88dbf6432ec8e4e67be69af0fda193e5b6d02e3c9acb7655f7811e8` |
| `head_on_corridor_low_test_s03000_eval_bc_a0_dwb` | bc | head_on_corridor | low | timeout; terminal 4.0 s net goal progress 0.102 m < 0.150 m | `data/raw/head_on_corridor_low_test_s03000_eval_bc_a0_dwb.jsonl` | `ab8f951287ec2e025807ecddb45fab003b6bd63a3a7e2e450b5878f12938e9d1` |

### Timeout with terminal progress

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_low_test_s03300_eval_bc_a0_dwb` | bc | blind_corner | low | timeout; terminal 4.0 s net goal progress 0.584 m >= 0.150 m | `data/raw/blind_corner_low_test_s03300_eval_bc_a0_dwb.jsonl` | `b671140480b2b56e0c751b64d4c686725525923414ded3474e349d98fa54ef9b` |
| `opposite_streams_high_test_s03620_eval_bc_a0_dwb` | bc | opposite_streams | high | timeout; terminal 4.0 s net goal progress 0.232 m >= 0.150 m | `data/raw/opposite_streams_high_test_s03620_eval_bc_a0_dwb.jsonl` | `53825d3d32ced5f75304c9ad601847cd34e5b190b592ded8c78a7ce2753d5464` |
| `overtaking_low_test_s03500_eval_bc_a0_dwb` | bc | overtaking | low | timeout; terminal 4.0 s net goal progress 0.958 m >= 0.150 m | `data/raw/overtaking_low_test_s03500_eval_bc_a0_dwb.jsonl` | `bc358e6ae2d75fe35e49da7350c8861a91ad18147f3d2431c17c5be248d228cc` |

### Timeout, terminal progress unavailable

No final episode was assigned to this category.

### Planner abort

No final episode was assigned to this category.

### Simulator failure (excluded)

No final episode was assigned to this category.

### Invalid reset (excluded)

No final episode was assigned to this category.

## Interpretation boundary

This artifact supports counts, terminal contact labels explicitly supplied by the evaluator, terminal goal-progress observations, and recorded recovery activity. It does not by itself establish that a trigger, WAIT/BACKUP choice, planner decision, or pedestrian behavior caused a terminal outcome.
