# Claim--Evidence Matrix

The held-out three-density Gazebo artifacts (internal protocol ID
`moderate-v5`) are authoritative only after
`scripts/reproduce_paper.sh` completes. The paper imports numerical claims from
`paper/generated/moderate_result_macros.tex`; no exploratory value or previous
evaluation is a substitute. Statistical wording must be checked against the
global Holm-adjusted values in
`outputs/moderate/final/pairwise_statistics.json`.

| Claim or boundary | Direct evidence | Paper location | Statistical requirement | Counterevidence / limit |
|---|---|---|---|---|
| The final comparison covers the complete test-frozen, held-out three-density Gazebo benchmark. | `episode_manifest.parquet`, `run_manifest.json`, and the completeness checks in `summarize_moderate.py` and `moderate_artifacts.py` require 120 identical condition keys for each of `base`, `standard`, `heuristic`, `bc_uniform`, and `pgrr`. | Scenarios, Splits, and Comparators; `moderate_main_results.tex` | Integrity claim; no hypothesis test. | Infrastructure attempts remain recorded and are reported separately. |
| PGRR changes goal-reaching, collision, and timeout rates relative to Base DWB. | `results.parquet`; `moderate_result_macros.tex`; Base comparison in `pairwise_statistics.json`. | Abstract, Results, Conclusion; main-results and paired-statistics tables. | Report the paired estimate, bootstrap interval, exact McNemar test, and globally Holm-adjusted value. Use significance language only when the generated adjusted value supports it. | A collision change is not a completion improvement; timeout and planner failure remain separate. |
| PGRR is compared with four complete paired baselines. | All comparator blocks in `pairwise_statistics.json`; `moderate_paired_effects.pdf`; `moderate_pairwise_statistics.tex`. | Paired Effects Against Four Baselines | One global Holm family covers every registered comparator--endpoint test. | Do not select a favorable family, density, or seed after evaluation. |
| The four baselines isolate distinct components: no project recovery, Arena standard recovery, deterministic masked selection, and non-aggregated Uniform BC. | Frozen `configs/planner/baselines.yaml`, method/checkpoint hashes in `run_manifest.json`, and identical-condition pairing. | Scenarios, Splits, and Comparators | Component-definition claim; closed-loop differences still reflect each complete stack. | Base and Standard intentionally do not receive the PGRR supervisor; Heuristic and Uniform BC share PGRR's detector, state machine, mask, and supervisor. |
| Effects vary with density or interaction geometry. | `moderate_density_results.tex`, `moderate_outcomes_and_density.pdf`, and `moderate_family_success.pdf`. | Closed-Loop Navigation Outcomes | Descriptive unless an explicitly predeclared interaction test is added. | Cell counts are shown; visual differences alone are not significance claims. |
| Recovery behavior is active and auditable. | Per-episode trigger, recovery-success, duration, intervention, and emergency-stop fields; `moderate_recovery_metrics.tex`. | Recovery Behavior | Descriptive means/SDs unless included in the paired statistics JSON. | The detector, mask, policy, Nav2, and supervisor act jointly. |
| The shared pedestrian swept-step guard does not favor a method or suppress robot collision outcomes. | One scenario hash and actor-dynamics profile are paired across methods; actor-controller code changes pedestrian steps only; the episode logger independently classifies physical robot--pedestrian contact. | Platform and Robot; Limitations | Implementation and protocol claim only. | The guard is a simplified responsive-pedestrian model and limits ecological validity. |
| Observable closing-side and side-commitment guards constrain only already-legal recovery actions. | Frozen `recovery_state_machine.yaml`, recovery telemetry, and mask/state-machine tests. | Recovery Actions, Mask, and Supervisor | Configuration and implementation claim only; no isolated causal effect is claimed. | Beam-count and commitment-horizon settings are validation selected and provide no formal safety guarantee. |
| DAgger and masking affect offline decision quality. | Frozen offline diagnostic CSV/JSON and `offline_ablation.tex`. | Offline Imitation and Mask Diagnostics | Scenario-disjoint validation only; no closed-loop causal claim. | Mask-disabled rows are counterfactual and are never executed. Margin weighting remains a negative result. |
| The two-round DAgger workflow was completed, but the selected checkpoint uses the accepted aggregate plus a train-only coverage shard rather than the second-round candidate. | DAgger manifests, selected checkpoint manifest, train-split shard metadata, and checkpoint hash. | Behavior Cloning and DAgger; Scenarios, Splits, and Comparators | Model-selection provenance; no test evidence is used. | The unselected second-round candidate is retained as a negative selection result. |
| The privileged expert provides planning supervision. | Expert rollout code, label shards, candidate costs, and `action_space_expert.pdf`. | Privileged Planning Expert | Training/diagnostic reference only. | The expert uses simulator state; no optimality or deployment claim is made. |
| PPO, a learned detector, cross-simulator transfer, and hardware deployment are not contributions of this release. | Selected configuration, checkpoint metadata, and method text. | Method and Limitations. | Not applicable. | The title and contribution list claim imitation learning only. |

## Authoritative held-out Gazebo artifacts (internal ID: moderate-v5)

- `outputs/moderate/v5_validation/calibration_report.json`
- `outputs/moderate/final/episode_manifest.parquet`
- `outputs/moderate/final/run_manifest.json`
- `outputs/moderate/final/results.parquet`
- `outputs/moderate/final/summary.csv`
- `outputs/moderate/final/pairwise_statistics.json`
- `outputs/moderate/final/failure_analysis.md`
- `paper/generated/moderate_*.tex`
- `paper/figures/moderate_*.pdf`
- `paper/main.pdf`

Any stronger wording requires a new versioned experiment and regenerated
artifacts; exploratory logs and screenshots are qualitative context only.
