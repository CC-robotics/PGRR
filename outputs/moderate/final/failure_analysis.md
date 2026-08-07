# Final Failure Analysis

This report is generated from the locked final result table only. It describes terminal outcomes and recorded telemetry; it does not infer causal mechanisms that are absent from those artifacts.

## Provenance and scope

- Source: `outputs/moderate/final/results.parquet`
- Source SHA-256: `77a1c2eb57279252e09624fad4aa57828f409426c2aa3f5c2b631556614aba97`
- Project commit recorded by all rows: `6916e7cd586acfbe200045e49b093039e2a6980e`
- Manifest result rows: 600
- Algorithm episodes: 600
- Excluded terminal rows: 0
- Excluded physical attempts retained by the runner: 14

## Classification policy

- `collision_human` and `collision_static` require an explicit contact type in   `outcome_detail`. A generic LiDAR or collision message remains   `collision_unattributed`.
- `timeout_stagnation` means less than 0.150 m net   goal-distance progress in the final 4.0 s, computed from the   stored timeline. It is a kinematic observation, not a diagnosis of why progress   stopped.
- `planner_abort` is assigned only to the terminal `PLANNER_FAILURE` outcome.
- Simulator failures and invalid resets are shown separately and remain excluded   from algorithm metrics.

## Category totals

| Category | Count | Metric scope |
|---|---:|---|
| Human collision | 59 | algorithm |
| Static-geometry collision | 17 | algorithm |
| Collision, contact type unresolved | 0 | algorithm |
| Timeout / terminal stagnation | 13 | algorithm |
| Timeout with terminal progress | 0 | algorithm |
| Timeout, terminal progress unavailable | 0 | algorithm |
| Repeated recovery exhausted | 32 | algorithm |
| Planner abort | 0 | algorithm |
| Simulator failure (excluded) | 0 | excluded technical outcome |
| Invalid reset (excluded) | 0 | excluded technical outcome |

## Counts by method, scenario family, and density

Only observed non-success categories are listed; zero-count categories remain visible in the totals above.

| Category | Method | Family | Density | Episodes |
|---|---|---|---|---:|
| Human collision | base | blind_corner | high | 1 |
| Human collision | base | crossing_flow | low | 1 |
| Human collision | base | crossing_flow | medium | 5 |
| Human collision | base | crossing_flow | high | 2 |
| Human collision | base | doorway_bottleneck | low | 2 |
| Human collision | base | doorway_bottleneck | medium | 1 |
| Human collision | base | head_on_corridor | low | 2 |
| Human collision | base | head_on_corridor | high | 2 |
| Human collision | base | temporary_blockage | low | 4 |
| Human collision | base | temporary_blockage | medium | 3 |
| Human collision | base | temporary_blockage | high | 5 |
| Human collision | heuristic | crossing_flow | medium | 1 |
| Human collision | standard | blind_corner | high | 2 |
| Human collision | standard | crossing_flow | medium | 5 |
| Human collision | standard | crossing_flow | high | 2 |
| Human collision | standard | doorway_bottleneck | low | 2 |
| Human collision | standard | doorway_bottleneck | medium | 1 |
| Human collision | standard | head_on_corridor | low | 2 |
| Human collision | standard | head_on_corridor | high | 4 |
| Human collision | standard | temporary_blockage | low | 4 |
| Human collision | standard | temporary_blockage | medium | 3 |
| Human collision | standard | temporary_blockage | high | 5 |
| Static-geometry collision | base | blind_corner | low | 2 |
| Static-geometry collision | base | blind_corner | medium | 2 |
| Static-geometry collision | base | blind_corner | high | 3 |
| Static-geometry collision | bc_uniform | blind_corner | high | 1 |
| Static-geometry collision | standard | blind_corner | low | 4 |
| Static-geometry collision | standard | blind_corner | medium | 3 |
| Static-geometry collision | standard | blind_corner | high | 2 |
| Timeout / terminal stagnation | bc_uniform | blind_corner | low | 1 |
| Timeout / terminal stagnation | bc_uniform | blind_corner | high | 2 |
| Timeout / terminal stagnation | bc_uniform | temporary_blockage | medium | 1 |
| Timeout / terminal stagnation | bc_uniform | temporary_blockage | high | 1 |
| Timeout / terminal stagnation | heuristic | blind_corner | low | 1 |
| Timeout / terminal stagnation | heuristic | blind_corner | high | 4 |
| Timeout / terminal stagnation | heuristic | temporary_blockage | medium | 1 |
| Timeout / terminal stagnation | pgrr | crossing_flow | low | 1 |
| Timeout / terminal stagnation | pgrr | temporary_blockage | medium | 1 |
| Repeated recovery exhausted | bc_uniform | blind_corner | low | 1 |
| Repeated recovery exhausted | bc_uniform | blind_corner | medium | 3 |
| Repeated recovery exhausted | bc_uniform | blind_corner | high | 1 |
| Repeated recovery exhausted | bc_uniform | doorway_bottleneck | medium | 2 |
| Repeated recovery exhausted | bc_uniform | temporary_blockage | medium | 1 |
| Repeated recovery exhausted | bc_uniform | temporary_blockage | high | 2 |
| Repeated recovery exhausted | heuristic | blind_corner | low | 1 |
| Repeated recovery exhausted | heuristic | blind_corner | medium | 2 |
| Repeated recovery exhausted | heuristic | head_on_corridor | low | 2 |
| Repeated recovery exhausted | heuristic | head_on_corridor | high | 3 |
| Repeated recovery exhausted | heuristic | opposite_streams | high | 2 |
| Repeated recovery exhausted | heuristic | overtaking | medium | 1 |
| Repeated recovery exhausted | heuristic | temporary_blockage | medium | 1 |
| Repeated recovery exhausted | heuristic | temporary_blockage | high | 1 |
| Repeated recovery exhausted | pgrr | blind_corner | low | 1 |
| Repeated recovery exhausted | pgrr | blind_corner | high | 2 |
| Repeated recovery exhausted | pgrr | doorway_bottleneck | medium | 2 |
| Repeated recovery exhausted | pgrr | temporary_blockage | low | 1 |
| Repeated recovery exhausted | pgrr | temporary_blockage | medium | 1 |
| Repeated recovery exhausted | pgrr | temporary_blockage | high | 2 |

## Recorded recovery behavior

The trigger and intervention columns below are descriptive aggregates from the final table. They are not used to attribute an outcome to the recovery policy.

| Method | Episodes | Non-success outcomes | Trigger count | Trigger mean | Recovery-timeline episodes | Intervention ratio mean | Non-CONTINUE samples | WAIT samples | BACKUP samples |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 120 | 35 | 0 | 0.000 | 0 | 0.033 | 0 | not recorded | not recorded |
| bc_uniform | 120 | 16 | 403 | 3.358 | 101 | 0.229 | 28816 | not recorded | not recorded |
| heuristic | 120 | 20 | 412 | 3.433 | 101 | 0.232 | 29128 | not recorded | not recorded |
| pgrr | 120 | 11 | 426 | 3.550 | 101 | 0.220 | 24942 | not recorded | not recorded |
| standard | 120 | 39 | 0 | 0.000 | 0 | 0.034 | 0 | not recorded | not recorded |

Action-specific counts for WAIT, BACKUP are not present in `results.parquet`; this report does not infer them from recovery state, terminal outcome, or free-text detail.

## Deterministic representative episodes

For each category, at most three rows are selected by a fixed method/family/density/episode ordering with method and family coverage preferred. The listed raw files are SHA-256 verified against the final result table.

### Human collision

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_high_test_moderate_v6_r00_s87320_eval_base_r95ec74c511bb_a0_dwb` | base | blind_corner | high | explicit outcome detail: privileged robot-human overlap | `data/raw/blind_corner_high_test_moderate_v6_r00_s87320_eval_base_r95ec74c511bb_a0_dwb.jsonl` | `3b2969e6d15e86241c2e3c5ad5fe1800357259628367bb61301c26d8cd999c41` |
| `crossing_flow_medium_test_moderate_v6_r02_s87212_eval_heuristic_r95ec74c511bb_a0_dwb` | heuristic | crossing_flow | medium | explicit outcome detail: privileged robot-human overlap | `data/raw/crossing_flow_medium_test_moderate_v6_r02_s87212_eval_heuristic_r95ec74c511bb_a0_dwb.jsonl` | `84077f1f108ee197e613342eca8d7acaa4796e485da1c50e912a231137851bd1` |
| `blind_corner_high_test_moderate_v6_r03_s87323_eval_standard_r95ec74c511bb_a1_dwb` | standard | blind_corner | high | explicit outcome detail: privileged robot-human overlap | `data/raw/blind_corner_high_test_moderate_v6_r03_s87323_eval_standard_r95ec74c511bb_a1_dwb.jsonl` | `13f30a4b111c84042512bb4768a4eb5b675e4c537814f99779e336f838dbc8bf` |

### Static-geometry collision

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_low_test_moderate_v6_r02_s87302_eval_base_r95ec74c511bb_a0_dwb` | base | blind_corner | low | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_low_test_moderate_v6_r02_s87302_eval_base_r95ec74c511bb_a0_dwb.jsonl` | `fb1c976f07129704f0f94a80c98539b27d59ddb3b547a29467f54d2f6b52a120` |
| `blind_corner_high_test_moderate_v6_r01_s87321_eval_bc_uniform_r95ec74c511bb_a0_dwb` | bc_uniform | blind_corner | high | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_high_test_moderate_v6_r01_s87321_eval_bc_uniform_r95ec74c511bb_a0_dwb.jsonl` | `5454d6ecd002ecabd9210d8eda7be553765875a2486458cece89a553d4ee39ca` |
| `blind_corner_low_test_moderate_v6_r00_s87300_eval_standard_r95ec74c511bb_a0_dwb` | standard | blind_corner | low | explicit outcome detail: physical robot footprint intersects known static scenario geometry | `data/raw/blind_corner_low_test_moderate_v6_r00_s87300_eval_standard_r95ec74c511bb_a0_dwb.jsonl` | `6753adc40020969ad9a87c76ffa87cd7ccd51e51db7a3d9b1464e42db00b6d61` |

### Collision, contact type unresolved

No final episode was assigned to this category.

### Timeout / terminal stagnation

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_low_test_moderate_v6_r03_s87303_eval_bc_uniform_r95ec74c511bb_a0_dwb` | bc_uniform | blind_corner | low | timeout; terminal 4.0 s net goal progress 0.000 m < 0.150 m | `data/raw/blind_corner_low_test_moderate_v6_r03_s87303_eval_bc_uniform_r95ec74c511bb_a0_dwb.jsonl` | `df21af532442e340726bf5e93b8432c08918be0e05c6d3845902cdbaa35f01cc` |
| `blind_corner_low_test_moderate_v6_r02_s87302_eval_heuristic_r95ec74c511bb_a0_dwb` | heuristic | blind_corner | low | timeout; terminal 4.0 s net goal progress 0.000 m < 0.150 m | `data/raw/blind_corner_low_test_moderate_v6_r02_s87302_eval_heuristic_r95ec74c511bb_a0_dwb.jsonl` | `4513a3713d34850bf2747a6403285a818752172527ab827e26cc5bbe839ba900` |
| `crossing_flow_low_test_moderate_v6_r00_s87200_eval_pgrr_r95ec74c511bb_a0_dwb` | pgrr | crossing_flow | low | timeout; terminal 4.0 s net goal progress 0.000 m < 0.150 m | `data/raw/crossing_flow_low_test_moderate_v6_r00_s87200_eval_pgrr_r95ec74c511bb_a0_dwb.jsonl` | `758c2f80fc6325959008ec7e65ea10a503419ab50379af25612b6a95f6c59540` |

### Timeout with terminal progress

No final episode was assigned to this category.

### Timeout, terminal progress unavailable

No final episode was assigned to this category.

### Repeated recovery exhausted

| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |
|---|---|---|---|---|---|---|
| `blind_corner_low_test_moderate_v6_r00_s87300_eval_bc_uniform_r95ec74c511bb_a0_dwb` | bc_uniform | blind_corner | low | global recovery-sequence duration exhausted without confirmed task progress | `data/raw/blind_corner_low_test_moderate_v6_r00_s87300_eval_bc_uniform_r95ec74c511bb_a0_dwb.jsonl` | `b5368d66cd579f0e73d2b8ecaa155154a500398875d22cf35d6ab839d5849c98` |
| `blind_corner_low_test_moderate_v6_r04_s87304_eval_heuristic_r95ec74c511bb_a0_dwb` | heuristic | blind_corner | low | global recovery-sequence duration exhausted without confirmed task progress | `data/raw/blind_corner_low_test_moderate_v6_r04_s87304_eval_heuristic_r95ec74c511bb_a0_dwb.jsonl` | `7ec4536632834521b82f16ccf2e23c2bb09fca20d484c42f9cc81b71dbb7815b` |
| `blind_corner_low_test_moderate_v6_r00_s87300_eval_pgrr_r95ec74c511bb_a0_dwb` | pgrr | blind_corner | low | global recovery-sequence duration exhausted without confirmed task progress | `data/raw/blind_corner_low_test_moderate_v6_r00_s87300_eval_pgrr_r95ec74c511bb_a0_dwb.jsonl` | `e6f9686e50617296a096e781d3bb643b86bd3d8a12d01815162085cab54e5e17` |

### Planner abort

No final episode was assigned to this category.

### Simulator failure (excluded)

No final episode was assigned to this category.

### Invalid reset (excluded)

No final episode was assigned to this category.

## Interpretation boundary

This artifact supports counts, terminal contact labels explicitly supplied by the evaluator, terminal goal-progress observations, and recorded recovery activity. It does not by itself establish that a trigger, WAIT/BACKUP choice, planner decision, or pedestrian behavior caused a terminal outcome.
