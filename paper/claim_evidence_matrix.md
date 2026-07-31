# Claim–evidence matrix

| Draft claim | Evidence | Artifact | Statistical status | Counterexample / limit |
|---|---|---|---|---|
| The learned policy executes bounded temporary-goal recovery and rejoins the original goal. | Three verified goal reaches with non-CONTINUE actions. | `outputs/pilot/crossing_flow_safety_aligned_repeat5.csv` plus raw SHA256 values | Execution claim only | Two retained timeouts. |
| The selected checkpoint never emits a masked action in offline validation. | Invalid action rate 0.0. | `checkpoints/dagger/coverage_safety_aligned/metrics.json` | Deterministic mask property | Requires at least one valid fallback. |
| Safety-aligned recovery has a favorable pilot signal against Base on high-density crossing flow. | Base 0/5 goals, 5/5 collisions; learned 3/5 goals, 0/5 collisions. | `outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json` | Not significant; Fisher $p=0.167$, wide exact intervals | Repeated one seed; two learned timeouts. |
| DAgger covers policy-induced recovery states. | Two aggregation rounds completed only on train split. | `data/manifests/dagger_iter1_manifest.json`, `data/manifests/dagger_iter2_manifest.json` | Pipeline provenance | DAgger-2 was worse in pilot and is a negative ablation. |
| The safety layer no longer traps the learned policy in the retained medium-density rear-obstacle counterexample. | Old policy timeout with 1275 recovery samples; corrected policy goal reach with 219. | `outputs/pilot/crossing_flow_medium_validation_escape_regression.csv` plus raw SHA256 values | Exact-scenario regression only | Base is faster on this scenario; no superiority claim. |

No final multi-scenario performance claim is authorized until the locked test artifacts exist.
