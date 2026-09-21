# PGRR extension v1: split and seed protocol

> Protocol draft only. No held-out test conditions are materialized by this script.

| Split | Seed base | Repeats per family-density cell | Allowed use |
|---|---:|---:|---|
| train | 91000 | 6 | expert labels, DAgger collection, and policy training only |
| validation | 93000 | 3 | checkpoint and ablation selection only |
| held_out_test (reserved, not materialized) | 97000 | 5 | reserve only; materialize after code/checkpoint/statistics freeze |

Seed formula: `seed = base + 100 * family_index + 10 * density_index + repeat_index`.
Split unit: complete episode. DAgger sources: train only. Model selection sources: train and validation only.
No scenario/seed/configuration hash/geometry may overlap across splits; moderate_v6_test remains excluded.
