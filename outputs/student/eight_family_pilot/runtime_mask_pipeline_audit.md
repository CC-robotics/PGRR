# PGRR runtime mask pipeline static audit

Source SHA-256: `55ca2b06f94bca5b22f79709e82420d2307e5b01f0883a33f046a4ff13b65c38`

| # | Scope | Call | Telemetry coverage | Source line |
|---:|---|---|---|---:|
| 1 | `_action_mask` | `compute_action_mask` | `upstream_unlogged` | 1003 |
| 2 | `_action_mask` | `apply_observable_scan_mask` | `upstream_unlogged` | 1025 |
| 3 | `_action_mask` | `apply_path_corridor_mask` | `upstream_unlogged` | 1047 |
| 4 | `_select_decision` | `self._action_mask` | `upstream_unlogged` | 1349 |
| 5 | `_select_decision` | `constrain_rejoin_actions` | `upstream_unlogged` | 1362 |
| 6 | `_select_decision` | `constrain_directional_yield_motion` | `logged_pre_post` | 1369 |
| 7 | `_select_decision` | `self._constrain_bc_temporal_closing_side` | `logged_pre_post` | 1382 |
| 8 | `_select_decision` | `constrain_near_field_subgoal_radius` | `logged_when_changed` | 1403 |
| 9 | `_select_decision` | `constrain_committed_lateral_side` | `logged_when_active` | 1420 |
| 10 | `_select_decision` | `constrain_stalled_rejoin` | `downstream_unlogged` | 1462 |
| 11 | `_select_decision` | `constrain_stalled_subgoals` | `downstream_unlogged` | 1463 |
| 12 | `_select_decision` | `constrain_repeated_replan` | `downstream_unlogged` | 1467 |
| 13 | `_select_decision` | `constrain_repeated_backup` | `downstream_unlogged` | 1472 |
| 14 | `_select_decision` | `constrain_net_retreat` | `downstream_unlogged` | 1477 |
| 15 | `_select_decision` | `constrain_stalled_wait` | `downstream_unlogged` | 1488 |
| 16 | `_select_decision` | `self._constrain_bc_recurrent_escape` | `logged_pre_final` | 1498 |
| 17 | `_select_decision` | `ensure_safe_wait_fallback` | `downstream_unlogged` | 1511 |
| 18 | `_select_decision` | `self._policy.select_action` | `inference` | 1512 |

This artifact verifies static source order only. It does not identify which rule
caused an episode outcome and it does not modify the runtime mask.
