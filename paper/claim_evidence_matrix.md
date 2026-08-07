# Claim--Evidence Matrix

The final three-density Gazebo artifacts are authoritative only if their run
manifest identifies `moderate_social_navigation_v6` and
`scripts/reproduce_paper.sh` completes all condition, provenance, and hash
checks. The paper imports numerical claims from
`paper/generated/moderate_result_macros.tex`; in its absence the LaTeX source
builds an explicit no-held-out-results version. Exploratory values, rejected
benchmark versions, validation episodes, and qualitative media are never
substitutes for the complete v6 test artifacts.

The protocol history is part of the evidence. Moderate-v5 was rejected before
test execution because its complete Base validation reached 57/72 goals
(79.17%), above the frozen 75% maximum. Moderate-v6 retains v5 geometry and
method settings, changes only Crossing Flow speed from 0.35--0.55 to
0.18--0.28 m/s, and uses new validation/test seed blocks 77000/87000. At the
v6 protocol freeze, its test split was unexecuted and uninspected.

An older, superseded v1 benchmark is retained as historical evidence, not as a
moderate-v6 result. Its checked-in 64/64 logical episodes establish a
safety--completion trade-off and are never pooled with, substituted for, or
used to make significance claims about moderate-v6.

| Claim or boundary | Direct evidence | Paper location | Statistical requirement | Counterevidence / limit |
|---|---|---|---|---|
| The public method is **PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation**. | `paper/main.tex`, release metadata, and the frozen runtime configuration. | Title; Abstract; Conclusion. | Naming claim only. | Historical `ramp_*`/`RAMP_*` interfaces remain compatibility names, not the public method name. |
| PGRR leaves NavFn/DWB in control during nominal navigation and temporarily selects 21 subgoals plus WAIT, BACKUP, REPLAN, and CONTINUE after observable failure triggers. | Runtime state/action telemetry, adapter tests, action-space tests, and `recovery_state_machine.yaml`. | Failure Trigger; Recovery Actions. | Implementation claim only. | The learned policy does not output velocity; Nav2 executes temporary and restored original goals. |
| The selected recurrent correction uses a 2.5 m bounded recurrent envelope, 0.60 m drift-aware turn clearance, a 3 s clear plus 0.25 m goal-progress budget reset, an 80-degree forward/reverse partition, and planner-failure handling. | Frozen `recovery_state_machine.yaml`, recovery-manager implementation, unit tests, and validation-only correction evidence. | Failure Trigger; Recovery Actions, Mask, and Supervisor. | Configuration/implementation claim; validation probe outcomes are descriptive only. | These constants were selected on validation and provide neither an isolated causal effect nor a formal safety guarantee. |
| Moderate-v5 failed calibration and was rejected without test inspection. | Complete Base validation rows and `outputs/moderate/v5_validation_comparators_d26d835/analysis/calibration_report.json`; decision log D-068. | Calibration Audit and v6 Freeze; artifact-gated Results. | 57/72 = 79.17% is compared with the preregistered [55%, 75%] acceptance band. | The threshold must not be widened after observing validation. No v5 test value is reportable. |
| Moderate-v6 makes exactly one interaction change and uses fresh split seeds. | `configs/experiments/scenario_catalog_moderate_v6.yaml`, compiled catalog manifest, and v6 split hashes. | Calibration Audit and v6 Freeze. | Protocol-integrity claim only. | Crossing Flow speed changes from 0.35--0.55 to 0.18--0.28 m/s; routes, lanes, clearances, radii, actor guard, and method are unchanged. Validation/test start at seeds 77000/87000. |
| Historical v1 records a safety--completion trade-off, not general navigation superiority: PGRR/Base collisions are 0/24 versus 19/24, timeouts 16/24 versus 0/24, and goal reaches 8/24 versus 5/24. | Checked-in `outputs/final/{run_manifest.json,results.parquet,statistics.json}` at historical project commit `35d7e601cd6f5baf168948a7174cd32fa9c37c5b`; the manifest completed 64/64 logical episodes. | Introduction; Historical v1 Safety--Completion Boundary; Conclusion. | The goal-reaching difference is not significant after global Holm adjustment (`p=0.75`); no completion-improvement claim. | This is a superseded v1 benchmark, not moderate-v5 or moderate-v6. It is never pooled with or substituted for v6 evidence. |
| A final comparison covers the complete test-frozen, held-out v6 benchmark. | Final `episode_manifest.parquet`, `run_manifest.json`, and completeness checks in `summarize_moderate.py` and `moderate_artifacts.py` must require 120 identical condition keys for each of `base`, `standard`, `heuristic`, `bc_uniform`, and `pgrr`. | Scenarios, Splits, and Comparators; generated main-results table. | Integrity claim; no hypothesis test. | This claim is absent when v6 artifacts are missing. Infrastructure attempts remain recorded and separate. |
| PGRR changes goal-reaching, collision, or timeout rates relative to Base DWB. | Complete v6 `results.parquet`; generated macros; Base comparison in `pairwise_statistics.json`. | Abstract; Results; Conclusion. | Report paired estimates, intervals, exact McNemar tests, and globally Holm-adjusted values. Use significance language only when the generated adjusted value supports it. | A collision change is not a completion improvement; every terminal category remains separate. |
| Base and PGRR may differ in `PLANNER_FAILURE` rate. | Complete v6 `results.parquet`; generated paper/report macros and `report_data.json`. | Closed-Loop Navigation Outcomes; complete terminal table. | Descriptive marginal rates and PGRR-minus-Base difference only; `PLANNER_FAILURE` is not a preregistered inferential endpoint and receives no post-hoc test. | Planner failure remains a terminal failure, not a success or infrastructure exclusion. |
| Base and PGRR may differ in duration or path length when both reach the goal. | `successful_episode_duration_s` and `successful_path_length_m` blocks in the Base comparison of `pairwise_statistics.json`; generated paper/report macros and `report_data.json`. | Paired Effects Against Four Baselines; technical report; deck slide 25. | Joint-success pairs only; report paired mean difference, bootstrap 95% CI, and global Holm-adjusted Wilcoxon value. | Conditioning on both methods succeeding cannot replace or delete collision, timeout, or planner-failure outcomes. |
| PGRR is compared with four complete paired baselines. | All comparator blocks in final `pairwise_statistics.json`; paired-effects figure/table. | Paired Effects Against Four Baselines. | One global Holm family covers every registered comparator--endpoint test. | Do not select a favorable family, density, seed, or outcome after evaluation. |
| The four baselines isolate no project recovery, Arena standard recovery, deterministic masked selection, and non-aggregated Uniform BC. | Frozen `configs/planner/baselines.yaml`, method/checkpoint hashes in the final run manifest, and identical-condition pairing. | Scenarios, Splits, and Comparators. | Component-definition claim; closed-loop differences reflect each complete stack. | Base and Standard intentionally omit the PGRR supervisor; Heuristic and Uniform BC share PGRR's detector, state machine, mask, and supervisor. |
| The reported environment is an executed Arena/ROS2 Humble/Gazebo/Jackal/NavFn/DWB/LiDAR stack, not only a schematic. | Runtime capture PNG plus metadata and raw capture log; pinned runtime/image and scenario hashes. | Platform and Robot; runtime Gazebo figure. | Qualitative platform evidence only. | A Gazebo GUI viewport is not an onboard robot-camera observation and does not supply outcome statistics. |
| The matched Base--PGRR trajectory and PGRR timeline are measured episode evidence. | Deterministic join from final `results.parquet` to both methods' raw JSONL, metadata, and outcome sidecars; renderer checks scenario, commit, and outcome equality. | Matched Execution Evidence. | Single-pair illustration only (`n=1`); no inferential claim. | These top-down panels are telemetry reconstructions, explicitly not camera screenshots. Terminal outcomes must be printed verbatim and never inferred visually. |
| Recovery behavior is active and auditable. | Per-episode trigger, recovery-success, duration, intervention, and emergency-stop fields; generated recovery table. | Recovery Behavior. | Descriptive means/SDs unless included in the paired statistics JSON. | The detector, mask, policy, Nav2, and supervisor act jointly. |
| The shared pedestrian swept-step guard does not favor a method or suppress robot collision outcomes. | One scenario hash and actor-dynamics profile paired across methods; actor-controller code changes pedestrian steps only; the logger independently classifies physical robot--pedestrian contact. | Platform and Robot; Limitations. | Implementation/protocol claim only. | The guard is a simplified responsive-pedestrian model and limits ecological validity. |
| Observable closing-side and side-commitment guards constrain only already-legal recovery actions. | Frozen state-machine configuration, recovery telemetry, and mask/state-machine tests. | Recovery Actions, Mask, and Supervisor. | Configuration/implementation claim only. | Beam-count and commitment-horizon settings are validation selected and provide no formal safety guarantee. |
| DAgger and masking affect offline decision quality. | Frozen offline diagnostic CSV/JSON and generated offline-ablation table. | Offline Imitation and Mask Diagnostics. | Scenario-disjoint validation only; no closed-loop causal claim. | Mask-disabled rows are counterfactual and never executed. Margin weighting remains a negative result. |
| The two-round DAgger workflow completed, but validation selected the accepted aggregate plus a train-only coverage shard, not the second-round candidate. | DAgger manifests, selected-checkpoint manifest, train-split shard metadata, and checkpoint hash. | Behavior Cloning and DAgger; Comparators. | Model-selection provenance; no test evidence is used. | The unselected second-round candidate is retained as a negative selection result. |
| The privileged expert provides planning supervision. | Expert rollout code, label shards, candidate costs, and action-space figure. | Privileged Planning Expert. | Training/diagnostic reference only. | The expert uses simulator state; no optimality or deployment claim is made. |
| PPO, a learned detector, a second planner, Flatland, hardware deployment, and formal safety are not contributions of this release. | Selected configuration, checkpoint metadata, method text, and limitations. | Method; Limitations. | Not applicable. | The release claims the validated imitation-learning recovery layer only. |

## Protocol and authoritative artifact locations

- Rejected v5 calibration audit (validation only):
  `outputs/moderate/v5_validation_comparators_d26d835/analysis/calibration_report.json`.
- Historical v1 frozen-test evidence (superseded; never a moderate-v6 input):
  `outputs/final/{run_manifest.json,results.parquet,statistics.json}`.
- Frozen v6 protocol: `configs/experiments/scenario_catalog_moderate_v6.yaml`,
  `scenarios/manifests/scenario_catalog_moderate_v6.json`, and
  `scenarios/splits/moderate_v6_{validation,test}.yaml`.
- Authoritative final directory, only after its manifest identifies v6 and all
  completeness gates pass: `outputs/moderate/final/` containing
  `episode_manifest.parquet`, `run_manifest.json`, `results.parquet`,
  `summary.csv`, `pairwise_statistics.json`, and `failure_analysis.md`.
- Generated numerical paper artifacts: `paper/generated/moderate_*.tex` and
  `paper/figures/moderate_*.pdf`.
- Actual-environment capture evidence:
  `paper/figures/runtime_gazebo_doorway_bottleneck_medium.png` and its runtime
  capture metadata outside the paper tree.
- Final anonymous manuscript: `paper/main.pdf`.

Any stronger wording requires complete versioned v6 artifacts and a regenerated
paper. Validation logs, rejected v5 results, telemetry reconstructions, and
Gazebo screenshots are retained for audit or qualitative context only.
