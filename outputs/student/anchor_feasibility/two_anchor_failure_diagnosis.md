# Two-anchor recovery failure diagnosis

> Two train-only runs. Descriptive evidence only; no causal or superiority claim.

| Anchor | Base | PGRR | Final goal distance | Cycles | Positive cycles | Rejoins | WAIT/BACKUP-only masks |
|---|---|---|---:|---:|---:|---:|---:|
| `goal_approach_lateral_interruption` | COLLISION | TIMEOUT | 4.61 m | 1 | 0 | 0 | 5/5 |
| `lead_pedestrian_sudden_stop` | COLLISION | TIMEOUT | 11.79 m | 5 | 0 | 4 | 8/10 |

## Main result

Across both anchors, 6/6 recovery cycles cleared the diagnosed hazard, but 0/6 made meaningful task progress. The logged final mask allowed only WAIT/BACKUP for 13/15 learned decisions.

This points first to a candidate-availability bottleneck, not simply a bad choice among many safe subgoals. It is not yet causal attribution because these historical runs did not record every upstream mask layer exactly.

## Next gate

Run one non-frozen, full-layer mask-trace episode for each anchor. Only after the exact removal layer is identified should candidate filtering or policy logic change. Do not tune on the frozen test set.
