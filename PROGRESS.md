# Progress

## Final project state

All planned release gates are complete:

1. The Ubuntu 22.04 / ROS2 Humble / Arena Gazebo runtime is pinned and isolated
   from the Python 3.10 `ramp-offline` environment.
2. Base DWB, Standard Nav2 recovery, deterministic Heuristic recovery, Uniform
   BC, and PGRR share one configurable runner, scenario set, terminal-outcome
   schema, and retry policy.
3. The observable trigger covers collision risk, freeze, oscillation,
   deadlock, and planner failure. The recovery state machine preserves the
   original goal and rejoins the classical planner after progress resumes.
4. The privileged rollout expert, behavior cloning, and two DAgger rounds are
   complete. The validation-selected checkpoint is
   `checkpoints/final/best.onnx`; PPO and a learned detector are not release
   claims.
5. The final benchmark calibration was accepted using validation only. The
   held-out test remained sealed until configuration, scenario, checkpoint,
   runtime, concurrency, and hashes were frozen.
6. Run `95ec74c511bb` completed all 600 logical episodes at evaluation commit
   `6916e7cd586acfbe200045e49b093039e2a6980e`.
7. Collection, paired statistics, global Holm correction, failure analysis,
   figures, tables, real-environment evidence, and matched-run telemetry were
   generated from checked-in artifacts.
8. The 8-page paper, 32-page technical report, 30-slide presentation, and
   96-file release manifest passed clean-checkout validation and privacy QA.

## Final result

| Method | Goal | Collision | Timeout | Planner failure |
|---|---:|---:|---:|---:|
| Base DWB | 85 | 35 | 0 | 0 |
| Standard | 81 | 39 | 0 | 0 |
| Heuristic | 100 | 1 | 6 | 13 |
| Uniform BC | 104 | 1 | 5 | 10 |
| PGRR | 109 | 0 | 2 | 9 |

Relative to Base, PGRR has +20.00 percentage points goal reaching and -29.17
points collision; both comparisons remain significant after the preregistered
global Holm correction. It also has efficiency and smoothness costs: on 83
joint successes it is 15.88 s slower and 1.89 m longer, and angular jerk is
higher. The preregistered goal/collision/timeout comparisons with Heuristic and
Uniform BC do not establish general superiority after global correction;
planner failure remains descriptive.

The execution audit is complete: 600 algorithm outcomes, eight excluded
`SIMULATOR_FAILURE` attempts, six excluded `INVALID_RESET` attempts, and 42
no-outcome launch commands across 39 unique tasks are all preserved. Resumes
filled only incomplete tasks and never replaced an algorithm outcome.

## Release outputs

- `outputs/moderate/final/`: final results, statistics, failure analysis,
  matched evidence, media, and manifest.
- `paper/main.pdf`: 8-page anonymous manuscript.
- `report/PGRR_technical_report_zh.pdf`: 32-page technical report.
- `presentation/PGRR_report_zh.pptx` and PDF: 30-slide briefing.
- `README.md` and `REPRODUCIBILITY.md`: canonical project and reproduction
  entry points.

Internal strings such as `moderate_v6` are frozen dataset/provenance IDs, not
additional product versions. Earlier milestones remain recoverable from Git
history instead of being listed as competing current states.

## Historical boundary

The earlier 64/64 audit is retained in every summary because it prevents an
overstated claim: PGRR/Base collisions were 0/24 versus 19/24, timeouts 16/24
versus 0/24, and goal reaches 8/24 versus 5/24; adjusted goal-reaching was not
significant. It is not pooled with the final result.

## Student extension development (2026-09-09)

Eight train-only Arena prototypes now have one Base runtime smoke each and
privileged actor-motion audits. A separate executable development protocol is
pinned at `configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml`.
Its validator confirms all 8 scenario hashes and the selected checkpoint hash,
the seed/metadata contract, no held-out test materialization, and a staged
32-attempt pilot (16 Base/PGRR, then 16 Heuristic/Uniform BC). This work is not
part of the final 600-episode release evidence and supports no superiority or
generalization claim.

The minimal paired pilot is complete: 8/8 Base--PGRR pairs and 16 valid
algorithm episodes.
Family 1 timed out for both methods and did not trigger PGRR. In family 2,
Base collided with static scenario geometry while PGRR triggered repeated
WAIT/BACKUP recovery and rejoin cycles, avoided collision, but timed out.
These are incomplete development results, not paper comparisons. Results and
raw-artifact hashes are collected under `outputs/student/eight_family_pilot/`.
In family 3, an initial Base `SIMULATOR_FAILURE` was preserved and the valid
`retry01` was selected. Base and PGRR both timed out, but Base ended 1.32 m
from the goal versus 13.91 m for PGRR; PGRR issued 56 recovery decisions.
This is retained as evidence of over-recovery and impaired progress.
In family 4, Base ended in a privileged robot--human collision. PGRR recorded
no collision but remained near the start and ended in `PLANNER_FAILURE` due to
`recovery_sequence_timeout`, with 20 WAIT and 9 BACKUP decisions and no
temporary subgoal or original-goal restoration. This is collision avoidance
without task recovery, not a successful navigation episode.
In family 5, the initial Base startup `SIMULATOR_FAILURE` was preserved and
`retry01` supplied the valid paired result. Base then collided with a dynamic
actor; PGRR timed out after 41 recovery decisions and five original-goal
restorations, with no temporary subgoal. Across the five incomplete development
pairs, neither method has reached the goal; no aggregate performance claim is
supported.
In family 6, Base collided with the stopped lead actor. PGRR avoided the
recorded collision but timed out at nearly the same goal distance after 28
decisions, four original-goal restorations, and one `SUBGOAL_0` decision. The
current evidence continues to show collision avoidance without restored task
completion in these strong-blockage development examples.
Across all eight train-only development pairs, Base produced six collisions
(five dynamic-actor and one static-geometry) and two timeouts. PGRR produced
seven timeouts and one planner failure, with no collisions but also no goal
reaches. PGRR triggered in 7/8 pairs, issuing 235 decisions, four temporary
subgoals, and 19 original-goal restores. Two zero-sample infrastructure
attempts are preserved separately. Because the minimal-pair health criterion
failed, the Heuristic/Uniform BC comparator phase remains paused pending
failure-mode quantification and a new train/validation development decision.
The first raw-trace failure-mode diagnostic is now complete. All eight selected
PGRR JSONL hashes match the collected provenance. Seven episodes made positive
net progress toward the original task goal, but none completed. Across 30
recovery cycles, only five ended closer to the original goal and 25 had
nonpositive progress; 23 cycles returned to normal navigation. Recovery-related
states occupied 39.2% of aggregate elapsed time, and the mean low-linear-speed
sample fraction was 22.4%. This identifies repeated, low-yield recovery as the
next train/validation development target; it does not by itself establish DAgger
overfitting or justify changing the frozen release.
Cycle-level attribution has also been generated for the same eight raw logs.
Collision risk was the dominant positive trigger score in 20 cycles, and 18
of those cycles had nonpositive original-goal progress. Twenty-five cycles
contained at least one learned-policy decision; 22 of those were nonpositive.
Of 60 learned-policy action events, 54 (90%) were WAIT or BACKUP. All five
numerically positive cycles occurred in recurrent bidirectional crossing, and
their maximum progress was only 0.169 m. These descriptive train-only counts
motivate a progress-aware recovery-interface design and controlled validation
ablations, but they do not identify causal responsibility or establish DAgger
overfitting.
A runtime-agnostic recovery-cycle assessment prototype now exists at
`packages/ramp_core/ramp_core/recovery/progress.py`. It evaluates observable
evidence for original-goal restoration, hazard clearance, task progress, and
rapid retrigger, and deliberately requires all thresholds from the caller. It
is not wired into ROS or the frozen state machine, so it changes no runtime
behavior. Its focused tests plus the existing recovery-option and state-machine
suite pass 176/176.
An offline JSONL adapter has now applied that interface to all 30 observed
recovery cycles using an explicit existing-contract probe (0.25 m progress,
four clear frames, `tau_off=0.35`, and a 2 s retrigger window). All 30 cycles
ended with the original task goal active and 28/30 met the clearance check,
but 0/30 reached 0.25 m of original-goal progress. The maximum was 0.169 m and
the median was -0.440 m. Fourteen cycles retriggered within 2 s; seven terminal
cycles had insufficient follow-up observation and were not treated as stable.
This further localizes the descriptive failure to post-recovery task progress,
without changing runtime behavior or assigning causal responsibility.
Read-only control attribution now separates final action masks, learned-policy
choices, and emergency-guard events. Of 60 learned decisions, 58 expose a
parseable final mask and 50/58 (86.2%) allow only WAIT/BACKUP. Eight retain an
alternative action; the policy chooses WAIT/BACKUP in four and a temporary
subgoal in four. No selected action falls outside its logged mask. Emergency
guards contribute 120 decision events, but immediately follow only 5/60 learned
events. The mask chain is therefore the first development hypothesis to test,
while policy conservatism and guard occupancy remain secondary, non-causal
hypotheses.
Layer-by-layer reconstruction of the same train-only logs now shows that 46/50
final WAIT/BACKUP-only masks were already restricted before the first
telemetry-recorded constraint. Three final collapses occur at
`bc_closing_side` and one at `bc_yield_mask`. The 46 upstream cases span seven
scenario families, so the next static audit targets base candidate construction
and earlier safety filtering. This is not a counterfactual ablation; no runtime
constraint was changed.
Static AST inspection now pins 18 runtime mask/inference stages to the current
`recovery_manager_node.py` hash. Supporting the logged `pre -> final` recurrent
escape format does not change the 46/3/1 attribution. Because rejoin filtering
only removes CONTINUE/REPLAN, the 46 pre-yield losses of all temporary subgoals
must arise in map/connectivity, observable-scan, or path-corridor filtering (or
their intersection). Per-layer causality remains unknown until synthetic replay.
A deterministic pure-Python replay now isolates the three upstream layers.
Retained temporary-subgoal counts after map/scan/corridor are 21/21/21 for an
open control, 0/0/0 for local map enclosure, 21/0/0 for close returns in every
LiDAR direction, and 21/21/3 for a 0.20 m straight path corridor. This proves
the layers are independently testable, not which layer caused the real 46
events. Existing raw-field sufficiency is the next read-only check.
Raw-field sufficiency is now audited for all 60 learned decisions with 8/8
source hashes verified. Robot pose, 180-bin resampled LiDAR, and a nonempty
global path are present for 60/60, allowing explicitly approximate scan and
corridor replay. Original scan geometry, occupancy-map snapshots, the latched
task-corridor path, and runtime mask-parameter snapshots are absent for 60/60,
so exact replay of any upstream layer is not supported.
Approximate scan-plus-corridor replay now covers 58 logged yield-mask inputs.
It exactly matches the logged temporary-subgoal set in 29/58 events. Of 46
logged empty subgoal sets, 27 are also empty in replay: 26 after the approximate
scan stage and one after the corridor stage. Nineteen remain unexplained by
the available scan/path record. Five events contain a logged-valid action that
the approximation rejects, confirming that this reconstruction is not exact
and cannot support causal attribution.
A runtime-agnostic `MaskTraceRecorder` now defines the proposed train-only
per-layer telemetry contract without being imported by ROS. It is disabled by
default, returns a detached copy of the observed output mask, requires unique
contiguous stages, and rejects undeclared action reauthorization. Four focused
tests cover disabled behavior, monotonic recording, contract violations, and
explicit special-action additions.
The trace recorder has now passed its pre-integration equivalence gate on four
production-core synthetic fixtures (open, map-enclosed, close-scan, and narrow
corridor). With tracing disabled versus enabled, every per-layer retained set
and the final deterministic selected action are identical; disabled mode emits
zero transitions and enabled mode emits three. ROS-level equivalence remains
unproven because the recorder is still not integrated there.
The recorder is now minimally integrated into the real ROS recovery manager at
the map/connectivity, observable-scan, and path-corridor stages. The new
`enable_upstream_mask_trace` parameter defaults false. Disabled mode preserves
the original decision reason; enabled mode appends telemetry while retaining
the selected action and confidence. The Arena runner now exposes a validated
default-zero `RAMP_ENABLE_UPSTREAM_MASK_TRACE` switch. A 222-test offline
regression, Ruff pass, and normalized Bash syntax check succeeded. No Arena
episode or frozen evidence was changed, so live ROS
message timing and log-size validation remain pending.
A reusable smoke preflight now rejects frozen paths, non-train scenarios, and
existing episode IDs, and verifies the default-off ROS/launcher contract. The
lead-stop PGRR trace smoke passed this preflight with `ready=true`. Actual Arena
execution is blocked because Docker is currently unavailable inside the WSL
distro and the WSL mirror lacks the new code/scenario; no simulator result is
claimed.

The opt-in mask telemetry has now run in a real non-frozen Arena train episode.
The successful retry produced 896 JSONL rows and a preserved TIMEOUT outcome;
110 decision rows each include all three upstream stages in the required order,
for 330 checked stage fragments. A checked-in validator also distinguishes the
two expected simulator shutdown tracebacks from recovery-manager failures.
Earlier failed attempts remain preserved with their COLLISION outcomes and
runtime causes. No threshold, model, frozen split, or final evidence changed.

Direct per-layer aggregation of retry02 is also complete. Map/connectivity
removes 0/2310 temporary-candidate instances. Observable scan removes 2280/2310
and first empties the set in 85 decisions; path corridor removes the remaining
30 candidates and first empties the other 25 decisions. Thus all 110 traced
decisions reach policy selection with no temporary subgoal. This result applies
only to one lead-stop train episode and requires replication before ablation.

Mask-trace replication added four preserved non-frozen episodes and an aggregate
report. A second trigger-positive train family (head-on corridor) reproduces
observable-scan elimination in 49/49 traced decisions. Across both positive
train episodes, scan first empties 134/159 decisions and corridor 25/159; map
never removes a temporary subgoal. The follow-up trigger audit distinguishes
two zero-score diagonal episodes from head-on validation, which reaches only
`EMERGENCY_STOP` and therefore emits no selector trace. Cross-split selector
replication remains open; the diagnostic script and JSON report are checked in.

The lead-stop compiler now supports an explicit train/validation split while
continuing to reject test. A validation candidate at seed 93500 was generated
with a preview and SHA-256 manifest, then passed the mask-trace runtime-contract
preflight under a fresh episode ID. Six focused compiler/preflight tests pass.
This completes static selection only; no Arena episode or performance claim was
added.

Added a read-only AST structural audit for Homework 2 and checked in its JSON
snapshot. It confirms that `RecoveryManagerNode` contains 52 methods across
1873 lines and quantifies the proposed 95-line observation seam versus the much
larger 426-line mask/policy seam. Together with existing progress-contract
tests, 20 focused tests pass. This is characterization evidence only; runtime
behavior and production source remain unchanged.

Added a generated Homework 3/paper claim ledger backed only by checked-in
development CSV/JSON. It records allowed wording and forbidden inference for
the minimal pair outcomes, recovery-cycle probe, mask traces, validation trigger
audit, and static preflight. Two focused tests verify the current numbers and
reject an unready preflight. No development number was inserted into the formal
paper and no held-out claim was made.

Implemented the first Homework 2 pure-Python module without wiring it into ROS:
`RecoveryObservationBuilder` reproduces the current observation-shaping
contract from explicit deployable inputs and excludes privileged fields by
signature. Tests cover fallback, padding, truncation, field propagation, and
invalid empty LiDAR; 16 focused tests and Ruff pass. Runtime behavior remains
unchanged pending a dual-path equivalence fixture.

Completed the offline dual-path fixture for the new observation builder. A
seeded 32-case probe compares an independent transcription of the current node
logic with the new pure builder across path, LiDAR, and history boundary cases;
every array field matches exactly. The JSON result, two probe tests, and Ruff
gate are checked in. No ROS rewiring was performed.

Added a read-only DAgger HDF5 label/mask audit with manifest-hash checks. The
canonical later iteration-5 train file is strongly WAIT-heavy (75.6%) and has a
median of one valid action, supporting a label/coverage-shift hypothesis. The
available iteration-3 alias and validation copy do not match their manifest
hashes, so the tool marks canonical comparison as not ready. One focused test
and Ruff pass; no model or frozen evidence changed.

Added a SHA-256 provenance search over current HDF5 files and all historical Git
HDF5 blobs. It confirms one matching manifest reference (later iteration-5
train) and three unresolved references: selected iteration-3 plus the shared
validation entry repeated by both manifests. One unit test and Ruff pass. No
file was restored, downloaded, renamed, or overwritten.

Ran the statically preflighted lead-stop validation development smoke in the
real Arena/Docker profile. The wrapper completed with a preserved TIMEOUT and
898 samples; 191/191 selector rows passed the ordered three-stage trace check,
with no malformed rows or recovery-manager runtime failure. The six-episode
summary and generated claim ledger now record 350 complete decisions and one
validation selector-positive episode. This closes cross-split diagnostic-path
replication only; it does not establish success, superiority, or a test result.

Added and tested a read-only timeout diagnostic for the lead-stop validation
episode. It hashes its inputs, reconstructs four recovery cycles, separates
pre/post-trigger task progress from travelled path length, and cross-tabulates
path-stage candidates, downstream directional-yield constraints, and selected
actions. All four cycles have nonpositive original-goal progress; 172 trace rows
end WAIT/BACKUP-only, 19 select REPLAN, and zero select a temporary subgoal. The
generated paper claim ledger now includes these numbers with an explicit
no-causality boundary. Four focused tests and Ruff pass.

Implemented the next Homework 2 safety seam: a default-off lazy observation
shadow comparator. Its disabled path never calls the candidate factory; its
enabled path records seven array-field errors, shape equality, and deployable
metadata equality without changing authority. The 32-case builder probe was
migrated to this comparator and still reports zero error. Eleven focused tests
and Ruff pass; production ROS wiring remains unchanged.

Added a constant-memory accumulator for observation shadow results. It tracks
comparison/equivalence counts, metadata mismatches, per-field mismatch counts,
and maximum errors without retaining any per-sample arrays. The existing probe
now emits this machine-readable summary: 32 comparisons, 32 equivalents, zero
mismatches. Twelve focused tests and Ruff pass; runtime remains untouched.

Audited mutable-input ownership before any ROS shadow wiring and fixed a real
side-effect risk: the builder now copies `base_action` before the immutable
observation container freezes its arrays. A new test mutates the source action
and LiDAR scan after construction and confirms the observation is independent
while both source buffers remain writable. Thirteen focused tests, Ruff, and the
32-case exact-equivalence probe pass.

Completed the first default-off ROS wiring for the observation shadow. The node
still returns only the legacy observation, while the lazy builder comparison is
recorded in a bounded accumulator when explicitly enabled. Static tests verify
the default, ordering, and deployable-only inputs; 38 related tests and Ruff
pass. A separate post-shadow structure report was created without overwriting
the fixed 1873-line pre-shadow baseline. Launcher forwarding and live non-frozen
runtime characterization remain pending.

Completed the launcher and preflight gate for observation-shadow runtime
characterization. The standard wrapper now validates a default-off `0/1`
switch, the inner launcher converts and forwards it as a ROS boolean, and a new
preflight rejects frozen/test/reused targets. A fresh lead-stop train episode is
ready but was not launched. Twenty-one focused tests, Ruff, Bash syntax checks,
and the machine-readable preflight all pass.

Added the runtime evidence contract needed before the observation-shadow smoke.
The ROS node emits one bounded aggregate only when shadowing is enabled, and a
new validator rejects missing, duplicate, mismatched, authority-changing, or
fatally interrupted summaries. Twenty-two tests and Ruff pass. No Arena episode
was executed and no navigation-performance claim was made.

Added a source-identity gate before the live observation-shadow smoke. The
preflight now pins five SHA-256 hashes and a read-only verifier blocks stale or
missing runtime files. The authoritative checkout self-check is 5/5, with 15
focused tests and Ruff passing. WSL synchronization and overlay rebuild remain
separate, explicitly unverified steps.

Completed the guarded WSL source synchronization. After a generic line-ending
attempt failed validation, an allowlisted backup-first synchronizer was added
and tested, then used to write exactly five LF-normalized files. WSL now reports
5/5 source matches and all Bash/Python syntax checks pass. No overlay build or
Arena run occurred during this step.

Attempted the next real gate, `make build`, after WSL source synchronization.
The build stopped before ROS compilation because the distro has no visible
Docker CLI and Docker Desktop WSL integration is inactive. Captured a
machine-readable blocker and preserved the 5/5 WSL source check. No image pull,
container run, training, or evaluation occurred.

Closed a failure-boundary gap in the Homework 2 shadow refactor: a broken
candidate builder can no longer abort the authoritative observation/control
path. The bounded summary records only error count and last exception type, and
the runtime validator still fails the diagnostic evidence. Twenty-three tests
pass, and the refreshed sources are synchronized to WSL at 5/5. No build or
Arena run was attempted while Docker integration remains unavailable.

Made the bounded observation-shadow summary safe for possible concurrent ROS
callbacks and teardown reads. Locked whole-record updates, locked snapshot
creation, and returned copies of nested dictionaries. An eight-thread,
1,000-operation test verifies exact counts and snapshot isolation. Twenty-four
tests pass, and WSL was refreshed to 5/5 without attempting a build or Arena.

Generated the Homework 3 eight-family algorithm-scenario-metric matrix from
checked-in YAML/CSV sources. The artifact covers 8/8 families and explicitly
separates per-episode outcomes, joint-success efficiency/smoothness costs, and
mechanism diagnostics. Current minimal pairs are labelled train-only and
descriptive; 3 focused tests, Ruff, and JSON parsing pass. No simulator,
training, locked test, or final evaluation was run.

Audited all 20 metrics requested by the eight-family matrix against the checked
runtime schema and existing derivation code. Eighteen are direct or derivable;
minimum clearance and deadlock duration have the necessary input telemetry but
still need preregistered operational definitions. Added JSON/Markdown outputs
and 3 passing unit tests. No Arena, training, or evaluation was run.

Built a reproducible two-anchor failure diagnosis from four checked train-only
artifacts. Both Base runs collided and both PGRR runs timed out; all 6 recovery
cycles cleared the diagnostic hazard, none made meaningful task progress, and
13/15 learned decisions had only WAIT/BACKUP in the final logged mask. Added
hash-bound JSON/Markdown outputs and 3 passing tests. No algorithm or runtime
change was made.

Restored the blocked runtime gate: Docker is visible in Ubuntu-22.04, WSL source
hashes match 4/4, and the ROS overlay builds 3/3 packages. Ran both non-frozen
train-only anchor diagnostics without changing policy or thresholds. Both
preserved TIMEOUT outcomes with 901 samples; 162 complete traces show
observable_scan first empties temporary subgoals in 123 decisions, versus zero
first-empty decisions at map or path layers. Thirteen focused tests pass.

Audited the 162 exact observable-scan transitions by action radius and direction.
All 69 collision-latched decisions are empty; no 1.4 m or forward/right-forward
candidate survives. The 180-beam approximate predicate replay is not sufficiently
exact for causal attribution (84.16% action agreement, 45.06% decision agreement).
Added reproducible JSON/Markdown outputs and 3 passing tests without changing runtime behavior.

Added opt-in original-LaserScan predicate telemetry, synchronized five hash-pinned
files with backups, rebuilt the ROS overlay (3/3), and reran both train-only anchors.
Both outcomes remain TIMEOUT. Strict validation accepts 192/192 traces, and exact
intersection checks localize all 122 scan-layer empty decisions to the swept-capsule
predicate. Twenty-seven related tests and Ruff pass; no algorithm threshold changed.

Extended the opt-in runtime diagnostics to locate swept-capsule failures and synced
six hash-pinned files with backups. The ROS overlay builds 3/3 packages. Two fresh
train-only anchors again preserve TIMEOUT and yield 89 valid decisions. Failures are
at segment interiors/endpoints, not initial overlap. Final temporary masks are empty
in all 89 decisions: 55 at scan and 34 after downstream directional yield. Forty-six
related tests and Ruff pass; no policy, threshold, frozen test, or final evidence changed.

Reconstructed the exact constraint intersection for all 89 latest anchor decisions.
The 34 scan-surviving decisions each retain only action 2 (0.6 m, -30 degrees), and
directional yield removes that action 34/34 times. A separate schema/geometry audit
finds neither anchor fully implements its named event: lead-stop lacks timed release,
and goal-approach is cyclic and unsynchronized. Added two reproducible JSON/Markdown
audits and 6 passing tests; retained all prior artifacts and made no algorithm change.

Added a hash-verified promotion-gate triage for all eight extension families. All
eight challenge Base and seven trigger PGRR, but no current PGRR development run
reaches the goal, so no family is yet core-comparison ready. The report routes one
family to trigger diagnosis, one to recovery/feasibility diagnosis, and six to event
semantics/feasibility work. Three focused tests and Ruff pass; no reruns were used to
replace failures and no frozen evidence was consulted.

Created and validated a train/validation-only event-control contract for the two
semantically incomplete anchors. The contract requires a single trigger, bounded
active phase, explicit release off the robot path, post-release task feasibility,
paired-method identity, and no privileged event state in policy inputs. Four tests
and Ruff pass. The artifact is deliberately non-executable and generated no test
scenario, training run, or evaluation result.

Implemented the contract's deterministic one-shot event state machine as an isolated
core Python module. It supports robot-actor and robot-goal distance triggers, requires
far-side arming, releases after a bounded duration, rejects time reversal, and resets
all episode state. Eight tests and Ruff pass. The module is not connected to ROS,
policy observations, executable scenarios, training, or evaluation.

Added a mapping adapter from the validated YAML variants to the isolated event state
machine and executed four deterministic offline traces (two events by train/validation).
All four contain exactly one activation and one release, and a source-isolation check
finds no policy observation/recovery dependency. Twelve combined tests and Ruff pass;
no ROS process or executable scenario was used.

Completed the read-only default-off ROS event-control wiring preflight. The current
tree has 7/7 prerequisites and intentionally has 0/6 runtime connections. Generated
a hash-bound JSON report defining the minimal actor-controller, reset, telemetry,
logger, generator, and launcher changes and their acceptance checks. Nineteen focused
tests pass; no runtime source behavior or frozen evidence was changed.

Implemented the preflighted default-off event-control wiring across the core runtime
adapter, ROS actor controller, episode logger, and launchers. Stale simulator truth
holds controlled actors, reset clears all event state, and transition data is kept out
of policy observations. Thirty-eight focused tests, Ruff, Python compilation, a 6/6
wiring inventory, and normalized-LF shell syntax checks pass. This is source-level
evidence only; no ROS overlay build or Arena event episode was run.

Materialized the first train-only bounded lead-stop candidate from the validated
event contract. The actor starts 5.0 m ahead, stops once at 3.0 m proximity for
3.0 s, then follows a noncyclic route through a far-end opening and finishes 3.441 m
off the robot path. A hash-bound manifest and preview were generated; Ruff and 17
focused tests pass. No WSL build, simulator run, seed search, test materialization,
policy change, or frozen-evidence change occurred.

Safely synchronized the event candidate runtime to WSL (9/9 hash matches with
backups), rebuilt 3/3 ROS packages, and ran the fixed Base/PGRR gate. Base produced
a valid TIMEOUT and physically demonstrated one event activation and release. PGRR
did not produce a valid comparative episode: the first attempt was a pre-event
SIMULATOR_FAILURE and the one same-seed retry failed startup topic readiness. Raw
artifacts and hashes are preserved; the candidate is explicitly not promoted.

Ran a historically stable non-frozen diagonal PGRR control, which completed as a
valid 893-sample TIMEOUT and confirmed runtime health. Generated and ran a same-seed
lead-stop v2 with an earlier event. Base collided and PGRR avoided that terminal
outcome but ended in recovery_sequence_timeout/PLANNER_FAILURE. Both event traces
are complete, yet Base's collision is classified as static geometry. Preserved the
pair as a valid negative result and rejected it from core-case promotion without
seed search, threshold tuning, or frozen-test use.

Ran the open-geometry event-controlled closing-gap candidate as a hash-pinned,
same-seed Base/PGRR train-only pair. Both episodes were valid and both actors completed
their activation and release transitions. Base and PGRR nevertheless timed out 2.151 m
and 2.067 m from the physical goal. Archived raw outcomes and trajectories and rejected
the candidate from core-case promotion; no seed search, policy change, or frozen-test
use occurred.

Implemented and tested a read-only selector for qualitative paper cases from the
already frozen final result. It verifies 26 Base-non-goal/PGRR-goal pairs across five
families and emits a deterministic eight-case CSV/JSON/Markdown shortlist. Ruff and
two focused tests pass. The output is explicitly labeled post-hoc and cannot replace
the complete 120-condition statistical analysis.

Audited every shortlisted case against the frozen results, local scenario files, raw
telemetry sidecars, and existing media. Generated a 40-row long-form five-method metric
table and machine-readable readiness report. Eight cases are ready for a descriptive
result table, no new trajectory can be honestly rendered from the current checkout,
and one case has existing SHA-verified publication media. Ruff and four focused tests
pass across the selector and audit.

Produced a complete Chinese supervisor-meeting brief covering work since the prior
feedback, verified results and negative findings, five current problems, paper evidence
boundaries, three proposed next-stage routes, four supervisor decisions, and a timed
one-hour discussion agenda. The brief preserves the frozen-result claims and does not
convert train-only diagnostics into publication conclusions.

Corrected the supervisor-facing research unit from “eight selected cases” to “eight
reproducible scenarios.” Added explicit warnings to the frozen-case shortlist and
evidence audit, updated the meeting brief, and recorded D-S55. The eight frozen rows are
now consistently described as auxiliary post-hoc examples; the eight new prototypes are
development negatives. Neither set is reported as completing the eight-scenario target.

Rewrote the Chinese supervisor report around three direct questions: what has been
completed, what concrete obstacles remain, and what must be agreed before the next
experiments. Removed the earlier route-heavy framing, retained the frozen quantitative
result and negative extension evidence, and reduced the requested supervisor decisions
to a focused set of experiment-defining questions.

Expanded the same supervisor report with an evidence-bounded Homework 2 section:
RecoveryManager structural baseline, pipeline contracts, CLI compatibility adaptation,
pure-Python observation builder, 32/32 exact offline equivalence, default-off ROS shadow,
failure containment, bounded/thread-safe summaries, source-hash gates, mask tracing, and
remaining Arena runtime-shadow/replacement boundaries. The report now asks five focused
supervisor questions, including the Homework 2 first-stage acceptance point.

Derived a fast scenario-discovery strategy from the frozen family-density summary and
extension failure diagnostics. The strongest existing anchor is crossing_flow/medium
(Base 0/5 goals and 5/5 collisions; PGRR 5/5 goals and 0/5 collisions). Documented eight
priority mechanisms, an offline-to-validation four-stage funnel, provisional 2-of-3
promotion criteria requiring PGRR goals, and stop rules that prevent seed search and
repeated reshaping of structurally unhealthy candidates.

Implemented and executed the first candidate in that funnel: a fixed-seed,
noncyclic, train-only medium crossing-flow anchor. Generated hash-bound JSON and a
preview, passed 7/7 offline checks, added a protected same-scenario Base/PGRR runner,
and passed 3 tests, Ruff, WSL shell syntax, checkpoint verification, and dry-run.
Corrected the generator to hash actual on-disk bytes across Windows/WSL. The real pair
did not start because Docker is unavailable, so no simulator or comparative claim was
recorded.

After Docker recovery, ran the pinned medium crossing-flow Base/PGRR pair end to end.
Base ended in privileged robot-human COLLISION at 272 samples; PGRR avoided collision,
completed one recovery/rejoin cycle, restored the original goal, and reached 3.917 m
from it, but TIMEOUT occurred at 900 samples. Archived both complete artifact sets and
rejected the candidate from promotion without seed search, timeout extension, threshold
tuning, or further scene shaping.

After identifying the systematic 22 m/90 s horizon confound, generated and ran the
design-corrected crossing-flow v2 with an exactly 15 m route and 6 m post-conflict
rejoin segment. All nine offline gates, four tests, Ruff, WSL syntax, hash and checkpoint
preflights passed. In the real fixed pair Base reproduced the dynamic collision at 271
samples, while PGRR recovered, used SUBGOAL_0 and SUBGOAL_7, restored the original goal,
and reached it at 757 samples. Archived both artifact sets. The scene advances only to
replicated train screening, not paper use.

Predeclared and executed two additional crossing-flow v2 train replicates without
changing geometry, timeout, checkpoint, thresholds, or seeds. Together with r00, Base
collided in 3/3 runs and PGRR reached in 3/3 after recorded recovery/rejoin transitions.
Preserved the r02 zero-sample INVALID_RESET and its single authorized same-seed retry,
then generated a deterministic JSON/Markdown gate summary. Six focused tests and Ruff
pass. The scenario passes train replication (1/8 candidate) but independent validation
and any new paper claim remain pending (0/8 validated).

Froze three independent validation seeds (96000-96002), a 2-of-3 terminal promotion
rule, and an infrastructure-only retry policy before execution. Generated three
hash-pinned 15 m scenarios, passed all offline gates and runner dry-run checks, and ran
all six Base/PGRR episodes without retries. Base collided dynamically in 3/3; PGRR
entered recovery/rejoin, restored the task goal, and reached in 3/3. Generated a
machine-readable recovery summary; eight focused tests and Ruff pass. Crossing-flow v2
is now independently validated as scenario 1/8, without touching frozen test evidence.

Locked the user's corrected four-scenario priority list in a machine-readable program
config and implemented the second mechanism, goal-approach lateral interruption. The
new open-geometry scene is exactly 15 m, triggers a one-shot crossing around 40 s,
releases the actor off-path, and preserves a 5 m rejoin segment. Nine offline gates,
two focused tests, and Ruff pass. In the real fixed-seed screen Base collided and PGRR
completed the event, recovery/rejoin, goal restoration, and goal reach. The preserved
zero-sample Base startup failure and sole retry remain auditable. Advance to 3-seed
train replication; do not yet count it beyond the existing 1/8 validated scenarios.

Predeclared, compiled, and executed the two missing goal-approach v2 train replicates.
Together with r00, all three pairs are Base dynamic collision versus PGRR goal reach;
each PGRR trace contains the event release and an original-goal-restored record. The
deterministic JSON/Markdown summary was generated, five focused tests pass, and Ruff
passes. Advance this frozen design to independently seeded validation; keep the fully
validated count at 1/8 until that gate is complete.

Froze validation seeds 98100--98102 and a 2-of-3 terminal rule for goal-approach v2,
then generated split-correct validation artifacts and ran all six valid episodes. Base
collided dynamically in 3/3; PGRR completed the event, recovery/rejoin, task-goal
restoration, and goal reach in 3/3. Generated a deterministic audit summary; six
focused tests and Ruff pass. This promotes goal-approach v2 to confirmed scenario 2/8.

Implemented and ran the third priority mechanism as a bounded two-pedestrian closing
gap. The 15 m v2 screen diagnosed insufficient terminal actor clearance rather than a
route-length confound. The same-seed v3 changed only terminal clearance from 1.7 m to
3.5 m: Base dynamically collided, while PGRR completed event release, recovery/rejoin,
goal restoration, and goal reach. Three focused tests pass and Ruff passes. Predeclare
additional train seeds next; do not count v3 beyond the existing 2/8 validated scenes.

Predeclared and ran the two additional bounded closing-gap v3 train pairs without
changing geometry, event timing, timeout, checkpoint, or thresholds. Base collided in
all three seeds, but PGRR produced GOAL_REACHED/TIMEOUT/TIMEOUT, so only 1/3 pairs
qualified and the 2/3 train gate failed. The two timeout traces finished 2.41 m and
2.01 m from goal after two nonpositive-progress recovery cycles each. Generated the
JSON/Markdown replication summary and per-run timeout diagnoses; five focused tests
and Ruff pass. Close this candidate before validation and proceed to a distinct design.
