# Claim--evidence matrix

Only the locked test and frozen offline ablation below authorize manuscript
claims. Development pilots remain useful regression history but are not pooled
with these results.

## Frozen evidence

- Experiment commit: `35d7e601cd6f5baf168948a7174cd32fa9c37c5b`
- Selected ONNX SHA-256: `78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2`
- Results SHA-256: `b8a60bf442ab7add77d7565bdfb0c1fecb3904070dab82f6350d2c5aa30362fc`
- Statistics SHA-256: `b05d618d21ca61d500bdefe529b247b74cca098bb5b125f28cfd92153c78c828`
- Bootstrap seed: `20260804`; 10,000 paired resamples; Holm family size 13

| Manuscript claim | Direct evidence | Figure/table | Statistical status | Boundary or counterevidence |
|---|---|---|---|---|
| The frozen run is complete and auditable. | `run_manifest.json` has 64/64 unique complete tasks and no worker error; 67 physical attempts include two `INVALID_RESET` and one `SIMULATOR_FAILURE` attempt retained before successful retries. | Main-results table (`Excl.`), artifact manifest | Integrity check, not a performance test | Infrastructure attempts are reported but excluded from algorithm rates. |
| PGRR avoided all contacts observed in the 24 primary pairs. | DWB: 19/24 collisions; PGRR: 0/24. Difference $-79.2$ percentage points, 95% paired bootstrap CI $[-91.7,-62.5]$. | Main-results and paired-statistics tables; density outcome figure | Exact McNemar raw $p=3.81\times10^{-6}$, Holm $p=4.20\times10^{-5}$ | This is an empirical Gazebo result, not a collision-free guarantee. |
| The collision reduction is primarily a completion trade-off. | DWB: 0/24 timeouts; PGRR: 16/24. Difference $+66.7$ points, CI $[45.8,83.3]$. | Main-results and paired-statistics tables; density outcome figure | Exact McNemar Holm $p=3.05\times10^{-4}$ | Collision avoidance must not be presented as recovery success. |
| PGRR's observed success rate is higher, but the evidence does not establish a significant success improvement. | DWB: 5/24; PGRR: 8/24. Difference $+12.5$ points, CI $[0.0,29.2]$. | Abstract macros; main-results and paired-statistics tables | Exact McNemar Holm $p=0.750$ | One seed per family--density cell and only three success-discordant pairs. |
| PGRR does not uniformly improve social or motion-quality metrics. | The adjusted minimum-distance and discomfort-time tests are not significant; intervention, emergency-stop count, and angular jerk increase. | Recovery and paired-statistics tables; safety--efficiency figure | All 13 tests receive Holm correction | PGRR has zero terminal contacts but a higher mean personal-space violation ratio and much more control intervention. |
| Benefits are condition-dependent. | PGRR reaches all crossing-flow and group-blocking goals and 2/3 temporary-blockage goals; all head-on, doorway, blind-corner, opposite-stream, and overtaking cells contain timeouts. | Density outcome figure; `failure_analysis.md` | Descriptive family cross-tab; one seed per cell | Family values are not per-family probability estimates. |
| Safe stagnation is the dominant learned-method failure. | Of 16 PGRR timeouts, nine have less than 0.15 m terminal four-second progress and seven retain terminal progress. Heuristic stagnates in 7/8 high-density episodes. | Failure Cases; generated failure report | Deterministic post-hoc taxonomy | The taxonomy describes kinematics and does not identify a causal action. |
| The hierarchy actually triggers, recovers, and rejoins in recorded runs. | PGRR averages 5.21 triggers/episode; its recovery-success mean is 73.6%; selected final telemetry includes a successful triggered crossing-flow episode. | Recovery table, recovery timeline, runtime sequence, final telemetry MP4 | Descriptive mechanism evidence | The safety supervisor and policy are both active, so closed-loop results do not isolate the network. |
| DAgger improves the selected policy's offline agreement and regret. | Uniform BC top-1/top-3/regret: 88.5%/95.7%/0.271; selected DAgger: 92.2%/98.5%/0.031 on the same 399 states. | Offline-ablation table | Fixed scenario-disjoint validation set | Offline agreement is not a substitute for closed-loop success. |
| Planning-mask enforcement prevents invalid executed proposals. | All three mask-enabled models have 0% invalid proposals offline; disabling the mask yields 93.2%, 93.2%, and 84.0% invalid proposals. | Offline-ablation table, action/expert figure | Deterministic offline ablation | Mask-disabled rows are counterfactual and were never executed in simulation. |
| Margin weighting is not a selected contribution. | Uniform BC and margin-weighted BC have identical mask-enabled decision metrics on this dataset. | Offline-ablation table | Negative ablation | The selected configuration has `margin_lambda: 0.0`. |
| The prescribed two-round DAgger workflow was completed without selecting a worse round. | Iteration manifests preserve both rounds; validation rejected DAgger-2. The frozen checkpoint extends the better first-round-aligned aggregate with a train-only head-on coverage shard. | Experimental Setup; DAgger manifests and selected checkpoint metrics | Validation-only model selection | The test split did not enter checkpoint selection. |
| PPO and a learned failure detector are not supported contributions in this release. | Frozen final config disables PPO and uses observable rule triggering. | Method, Limitations, README | Claim boundary | The title and contribution list contain imitation learning, not an asserted RL gain. |

## Authoritative artifacts

- `outputs/final/episode_manifest.parquet`
- `outputs/final/run_manifest.json`
- `outputs/final/results.parquet`
- `outputs/final/summary.csv`
- `outputs/final/statistics.json`
- `outputs/final/failure_analysis.md`
- `outputs/final/offline_policy_ablation.csv`
- `outputs/final/offline_policy_ablation.json`
- `paper/generated/*.tex`
- `paper/figures/*.pdf`

Any stronger wording requires a new versioned experiment, multi-seed replication,
and regeneration of this matrix; it cannot be justified from pilot artifacts.
