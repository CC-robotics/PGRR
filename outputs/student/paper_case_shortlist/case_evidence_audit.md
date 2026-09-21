# Eight-case evidence readiness audit

Results-table evidence ready: 8/8; local scenario files verified: 0/8; new trajectory rendering ready: 0/8; existing SHA-verified publication media: 1/8.

| # | Family | Density | Base | PGRR | PGRR triggers | Scenario | New plot | Existing media |
|---:|---|---|---|---|---:|---|---|---|
| 1 | `blind_corner` | medium | COLLISION | GOAL_REACHED | 10 | no | no | no |
| 2 | `crossing_flow` | medium | COLLISION | GOAL_REACHED | 1 | no | no | no |
| 3 | `doorway_bottleneck` | low | COLLISION | GOAL_REACHED | 1 | no | no | no |
| 4 | `head_on_corridor` | high | COLLISION | GOAL_REACHED | 2 | no | no | no |
| 5 | `temporary_blockage` | high | COLLISION | GOAL_REACHED | 9 | no | no | no |
| 6 | `blind_corner` | high | COLLISION | GOAL_REACHED | 14 | no | no | yes |
| 7 | `head_on_corridor` | high | COLLISION | GOAL_REACHED | 4 | no | no | no |
| 8 | `temporary_blockage` | high | COLLISION | GOAL_REACHED | 4 | no | no | no |

All eight cases can support a frozen-results table. New trajectory plots require the original JSONL and sidecars; their absence must not be replaced by rerunning or reconstructing unrecorded paths. The one existing publication figure remains explicitly labeled as telemetry reconstruction.
