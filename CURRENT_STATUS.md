# Current status

## Final release — complete

This repository now exposes one project state: **PGRR: Planning-Guided
Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation**. The
implementation, frozen evaluation, statistics, paper, technical report, and
presentation are complete. Names such as `moderate_social_navigation_v6` that
remain inside manifests and paths are immutable experiment identifiers, not
parallel product versions.

The authoritative held-out run is `95ec74c511bb`, recorded at evaluation
commit `6916e7cd586acfbe200045e49b093039e2a6980e`. It contains 600/600 logical
method--episodes: five methods evaluated on the same 120 conditions (eight
interaction families, three densities, and five repeats). The horizon is 240 s,
the frozen runner concurrency is six, and the final manifest reports no worker
errors.

| Method | Goal reached | Collision | Timeout | Planner failure |
|---|---:|---:|---:|---:|
| Base DWB | 85 | 35 | 0 | 0 |
| Standard Nav2 recovery | 81 | 39 | 0 | 0 |
| Heuristic recovery | 100 | 1 | 6 | 13 |
| Uniform BC | 104 | 1 | 5 | 10 |
| PGRR | 109 | 0 | 2 | 9 |

Against Base on 120 paired conditions, PGRR improves goal reaching by 20.00
percentage points (109/120 versus 85/120; global Holm-adjusted McNemar
`p=1.031e-4`) and reduces collision by 29.17 points (0/120 versus 35/120;
global Holm `p=2.561e-9`). The timeout difference is +1.67 points with global
Holm `p=1`. Planner failure is +7.50 points and is descriptive because it was
not a preregistered binary endpoint.

The result is not cost-free. On the 83 pairs where both Base and PGRR reach the
goal, PGRR takes 15.88 s longer (95% paired-bootstrap CI 11.43--20.83 s;
global Holm `p=3.318e-9`) and travels 1.89 m farther (CI 1.20--2.69 m; global
Holm `p=7.420e-7`). Mean absolute angular jerk is 0.185 rad/s^3 higher (global
Holm `p=4.585e-10`), while the observed +4.13-point personal-space violation
ratio is not significant after global correction (`p=1`). Comparisons against
Heuristic and Uniform BC on the three preregistered terminal endpoints (goal,
collision, and timeout) are also not significant after global correction;
planner failure remains descriptive. The supported claim is therefore a
safety and completion gain over Base DWB with measurable efficiency and
smoothness costs, not unqualified superiority over all recovery systems.

## Completeness and provenance

- All 600 algorithm outcomes are retained. Algorithm failures were never
  retried because they were unfavorable.
- The manifest retains 614 outcome-bearing physical attempts: 600 algorithm
  episodes plus eight `SIMULATOR_FAILURE` and six `INVALID_RESET` attempts
  excluded under the frozen infrastructure-failure rule.
- Attempt snapshots retain 42 commands without outcome files across 39 unique
  tasks. Resuming only incomplete tasks recovered all of them; none was
  converted into an algorithm outcome.
- The accepted calibration evidence is
  `outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json`, SHA-256
  `0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f`.
  The similarly named file under `outputs/moderate/final/` is an untracked,
  rejected empty-test byproduct and is not release evidence.
- `outputs/moderate/final/artifact_manifest.json` binds 96 release files to
  their hashes and records the evaluation commit independently from the
  document-generation commit.

## Delivered artifacts

- Anonymous paper: `paper/main.pdf` — exactly 8 pages.
- Chinese technical report: `report/PGRR_technical_report_zh.pdf` — exactly
  32 pages.
- Presentation: `presentation/PGRR_report_zh.pptx` and PDF — exactly 30
  slides/pages.
- Final result bundle: `outputs/moderate/final/`.
- Real Gazebo GUI evidence:
  `outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png`, explicitly
  labeled as a historical moderate-v5 validation environment capture
  (benchmark provenance, not another current release) rather than a camera
  frame from the held-out statistical run.
- Real same-condition Base--PGRR telemetry comparison:
  `outputs/moderate/final/media/moderate_matched_base_pgrr_trajectory.pdf` and
  `outputs/moderate/final/media/moderate_pgrr_recovery_timeline.pdf`, explicitly
  labeled as telemetry reconstructions rather than screenshots.

Development QA passed Ruff, formatting, mypy, 706 tests, exact document page
counts, PDF text/font checks, and document validators. The clean-checkout
release gate separately passed the privacy audit and byte-level verification of
all 96 manifest artifacts without modifying the checkout.

## Historical boundary retained for scientific honesty

An earlier frozen 64/64 audit remains a boundary on interpretation: across 24
Base--PGRR pairs, PGRR/Base collisions were 0/24 versus 19/24, timeouts were
16/24 versus 0/24, and goal reaches were 8/24 versus 5/24; the adjusted
goal-reaching comparison was not significant. Those rows are never pooled
with the final 600-episode result. The Git history and immutable manifests
retain the full development audit without presenting those milestones as
separate current releases.

## Remaining work

No implementation, simulation, statistics, or publication gate remains open.
Future work is limited to new research beyond this frozen release: reduce
planner failures, recovery duration, path overhead, social-space exposure, and
angular jerk, then evaluate on additional planners, maps, simulators, and
hardware without tuning on the existing held-out test.

## Student extension development

Separate train-only eight-family work has completed 8 Base--PGRR development
pairs. PGRR avoided the six recorded Base collisions but produced seven
timeouts and one planner failure, with no goal reaches. Raw-trace analysis
finds 25/30 recovery cycles with nonpositive original-goal progress and 90% of
learned action events concentrated in WAIT/BACKUP. A pure, unintegrated
recovery-cycle assessment interface now exists for offline validation. These
student artifacts do not alter or extend the frozen release claim.
The first offline contract probe covers all 30 cycles: 30 retain the original
goal, 28 clear the observable hazard, zero attain 0.25 m task progress, and 14
retrigger within 2 s. Seven cycles are correctly marked as having insufficient
post-rejoin observation rather than being counted as stable.
Control-attribution parsing further shows that 50/58 parseable learned-policy
events are restricted to WAIT/BACKUP before inference. This makes the mask chain
the next student-extension investigation target; no runtime mask or safety rule
has been changed.
The layer-by-layer student mask reconstruction localizes 46/50 final
WAIT/BACKUP-only masks to a point before the first telemetry-recorded
constraint. `bc_closing_side` accounts for three direct collapses and
`bc_yield_mask` for one. The next student task is an offline static map of
upstream candidate construction and a synthetic call-order fixture, not a
late-rule relaxation or model retraining.
An 18-stage static call-order audit now narrows the upstream temporary-subgoal
loss to map/connectivity, observable LiDAR, and path-corridor filtering. The
recurrent-escape `pre -> final` telemetry format is now parsed and leaves the
46/3/1 attribution unchanged. A synthetic three-layer replay fixture is next;
no runtime behavior has changed.
The first synthetic upstream replay is complete. An open control retains all
21 subgoals; an enclosed map and all-direction close LiDAR returns each remove
all 21 at their respective layers; a 0.20 m path corridor retains three
straight-ahead radii. This is fixture behavior, not real-episode causality.
The raw-field audit finds pose, resampled 180-bin LiDAR, and global path at all
60 learned decisions. Approximate scan/corridor replay is feasible, but exact
map, scan, or corridor replay is not: map snapshots, original scan geometry,
latched task-corridor paths, and runtime parameter snapshots were not logged.
Approximate real-event replay covers 58 yield decisions: 29 exact subgoal-set
matches, and 27/46 logged empty sets reproduced (26 at scan, one at corridor).
Nineteen empty sets remain attributable only to the omitted map layer or
logging/parameter fidelity. Five false eliminations prevent treating this as
an exact or causal reconstruction.
A pure, unintegrated mask-trace recorder now exists for the next train-only
diagnostic. It defaults off and enforces 25-action shape, stage uniqueness,
continuity, and explicit authorization of any added action. It does not alter
or instrument the ROS runtime yet.
Four synthetic production-core fixtures now pass trace-on/trace-off equivalence
for every upstream layer and the final deterministic action. This clears only
the pre-integration gate; the recorder remains absent from ROS.
The three-stage recorder is now present in the ROS recovery manager behind the
default-false `enable_upstream_mask_trace` parameter, and the episode runner
forwards a validated default-zero environment switch. Source-level integration,
syntax, lint, and 222 offline regression tests pass. It has not yet been enabled
in a live Arena train-only episode, so runtime logging equivalence is still an
open gate rather than a completed experimental result.
The prepared lead-stop mask-trace smoke passes a checked-in safety preflight:
train split, new episode ID, non-frozen paths, and complete opt-in launch
contract. Runtime execution is presently blocked by unavailable Docker/WSL
integration and an out-of-date WSL mirror. This is an environment blocker, not
a navigation outcome.

Docker/WSL integration was restored on 2026-09-12 and the ROS overlay built
successfully. After preserving two failed development attempts (a truncated
import from unsafe line-ending conversion and an integer-versus-bool ROS
parameter mismatch), retry02 completed with 896 telemetry rows and outcome
TIMEOUT. All 110 traced decision rows contain map/connectivity, observable-scan,
and path-corridor stages exactly once and in order. This closes the live
telemetry-path gate only; it is not a navigation-success or performance claim.

Within that single lead-stop train episode, direct trace attribution shows no
temporary-subgoal removal at map/connectivity, first emptying at observable scan
in 85/110 decisions, and first emptying at path corridor in 25/110. Every traced
decision has zero temporary subgoals after the corridor stage. This identifies a
development target for replication, not permission to relax safety thresholds.

Replication now covers five non-frozen episodes. Two selector-positive train
episodes contribute 159 complete traces: observable scan first empties the
temporary-subgoal set 134 times, path corridor 25 times, and map/connectivity
zero times. A trigger-coverage audit corrects the earlier coarse description:
the diagonal train/validation pair remains NORMAL with zero recorded failure
score, while head-on validation is emergency-stop-only (886/896 samples in
state 4) and never reaches temporary-subgoal selection. Validation-layer
replication is therefore still not established. The next gate is one preflighted
non-frozen validation prototype that reaches selector recovery with unchanged
thresholds, not blind retries or mask-threshold adjustment.

The next validation candidate is now materialized and statically preflighted:
`lead_pedestrian_sudden_stop_low_validation_r00_s93500`. It is non-frozen,
uses validation seed 93500, contains no test material, and passes all four
default-off mask-trace launch-contract checks with a fresh episode ID. It was
chosen because the same-family train episode reached selector recovery with
110 complete traces. No live run has been started, and static similarity does
not guarantee a selector trigger or establish held-out generalization.

Homework 2 now has a machine-readable pre-refactor structural baseline. The
recovery manager spans 1873 lines and 52 methods; its observation/geometry seam
is 9 methods and 95 lines, compared with 4 methods and 426 lines for mask/policy
selection. The report includes the source SHA-256 and internal method calls so a
later extraction can be compared against a fixed starting point. Twenty focused
structure/progress tests pass. No production ROS code was moved in this gate.

Homework 3/paper preparation now includes a generated extension evidence-to-
claim ledger. It binds five development statements to checked-in CSV/JSON and
records the forbidden inference for each: the eight train pairs, 30-cycle
progress probe, 159 mask traces, validation trigger-path audit, and unexecuted
lead-stop preflight. The ledger explicitly blocks superiority, causality,
runtime-completion, and held-out claims. Two focused tests pass; the formal
paper source and frozen release evidence remain unchanged.

Homework 2 now has an unused, ROS-independent `RecoveryObservationBuilder`
prototype. It preserves the node's path fallback, 5-scan LiDAR padding,
10-sample history padding/truncation, goal-polar conversion, and deployable
field shapes while accepting no privileged-human input. Sixteen focused
observation/encoding tests and Ruff pass. The ROS node has not been switched to
the builder, so runtime behavior and frozen evidence are unchanged.

The Homework 2 observation builder now passes an explicit dual-path offline
equivalence probe. With seed 92001, 32 cases cover empty/short/long paths,
1/2/5/7 LiDAR frames, and under/full/over-length histories. All seven array
fields have zero maximum absolute error and metadata matches. Five focused
tests and Ruff pass. This establishes covered pure-function equivalence only;
ROS callback timing and runtime rewiring remain untested and unchanged.

A read-only DAgger label/mask audit now shows that the manifest-matching later
iteration-5 train set is 75.6% WAIT with median one valid action. The available
iteration-3 alias is 32.4% WAIT with median six valid actions, but its SHA-256
does not match the selected manifest; the available validation copy also fails
its manifest hash. Therefore the distribution shift is a useful coverage/label
hypothesis, not a canonical selected-vs-later comparison or proof of overfit.
No training, checkpoint, or frozen test was touched.

The missing canonical DAgger inputs were then searched by content SHA-256
across every local `data/**/*.h5` and every historical Git HDF5 blob. Of four
manifest references, only the later iteration-5 train dataset is present; the
selected iteration-3 dataset and the shared validation hash are absent from both
current files and Git history. The search is recorded and tested. Recovery now
requires a trusted external backup/source, not renaming a local file or editing
the manifest to fit it.

The preflighted non-frozen lead-stop validation candidate has now been run with
unchanged thresholds and a fresh episode ID. It preserved a TIMEOUT outcome and
898 telemetry rows, while all 191 selector decisions contained complete ordered
map/connectivity, observable-scan, and path-corridor traces. This establishes
cross-split selector-layer diagnostic replication for the matched lead-stop
development family, not navigation success or held-out performance. Across the
six diagnostic episodes there are now 350 complete traced decisions; observable
scan first empties temporary subgoals in 306, path corridor in 29, and neither
does in 15.

A hash-bound timeout diagnostic now explains the observed validation trajectory
without changing the method. Before the first failure it made 9.886 m of task
progress; afterward it travelled 5.931 m but gained only 0.430 m toward the
original goal. All four bounded recovery cycles ended no closer than they began,
for -1.512 m combined cycle progress. Directional yield restricted 172/191
selector rows to WAIT/BACKUP (31/141), while the other 19 selected REPLAN; no
temporary subgoal was executed. This is a single-episode association, not causal
evidence or a threshold-change justification.

Homework 2 now has a default-off, lazy observation shadow comparator. When
disabled it does not evaluate the candidate builder; when enabled it reports
shape, per-field maximum absolute error, and metadata equality while explicitly
leaving the reference observation authoritative. The existing 32-case probe now
uses this comparator and remains exactly equivalent. Eleven focused tests and
Ruff pass. The comparator is not wired into ROS, so callback/runtime equivalence
is still unclaimed.

The observation shadow path now also has a bounded accumulator suitable for a
later long-running diagnostic smoke. It retains only counts and per-field
maximum errors, explicitly stores zero per-sample observations, and never
changes the authoritative path. The 32-case probe reports 32 equivalents, zero
mismatches, and zero maximum error for every field. Twelve focused tests and
Ruff pass; no ROS wiring or runtime logging was added.

A pre-wiring ownership audit found that the candidate builder could pass an
already-float32 `base_action` array through `np.asarray`, after which
`RecoveryObservation` would freeze the shared controller buffer. The builder now
copies that input, matching the legacy inline contract. A regression proves the
controller action and LiDAR inputs remain writable and unaliased. Thirteen
focused tests pass and the 32-case exact-equivalence result is unchanged.

The observation builder is now minimally wired into `RecoveryManagerNode` as a
default-off shadow only. The legacy inline observation is always constructed
first and remains the sole return value; the candidate is lazily evaluated only
when `enable_observation_shadow` is true, and aggregate discrepancies cannot
affect actions or state. Thirty-eight related tests and Ruff pass. The preserved
pre-shadow structural baseline remains 1873 lines/52 methods, while a separate
post-shadow snapshot records 1898 lines/52 methods. No Arena shadow run or
runtime-equivalence claim has been made.

The standard Arena launcher now forwards `RAMP_ENABLE_OBSERVATION_SHADOW`
through a strict default-off `0/1` contract and converts it to the ROS boolean
parameter. A reusable preflight rejects frozen paths, test scenarios, and reused
episode IDs while confirming that the legacy observation remains authoritative.
The selected non-frozen lead-stop train candidate is ready in a machine-readable
preflight artifact. Twenty-one focused tests, Ruff, and Bash syntax checks pass;
Arena has not been run for this gate.

Enabled observation-shadow runs now emit exactly one bounded JSON aggregate at
node teardown. A dedicated validator requires at least one comparison, exact
equivalence, zero per-sample retention, unchanged authority, and no recognized
runtime failure, while preserving the episode outcome without treating it as a
performance result. Twenty-two focused tests and Ruff pass. This is an evidence
contract only; no live Arena equality result exists yet.

The observation-shadow preflight now pins SHA-256 values for the five files that
must reach the WSL/Arena runtime. A read-only verifier reports missing or stale
runtime sources and performs no copying. Fifteen focused tests and Ruff pass,
and the authoritative Windows checkout self-checks at 5/5 matches. The WSL
checkout and built overlay have not yet been certified against this manifest.

The five preflight-pinned files are now synchronized into
`/home/preface/PGRR-online` by an allowlisted, backup-first, LF-normalizing
helper. A first generic line-ending conversion attempt was caught by the hash
and syntax gates before any build or run; the tested helper then restored exact
content. WSL now verifies 5/5 normalized hashes, both launchers pass `bash -n`,
and all three Python files compile. The ROS overlay is still not rebuilt.

An actual overlay build attempt stopped before compilation because Docker is not
visible inside `Ubuntu-22.04`; `docker image ls` and `docker container ls` both
report that Docker Desktop WSL integration must be activated. The synchronized
source gate remains 5/5. Docker Desktop could not be launched through unattended
app control because approval timed out, so no application setting was changed
and no Arena episode started.

The enabled-only observation shadow now contains ordinary candidate build or
comparison exceptions instead of allowing a diagnostic path to interrupt the
authoritative controller. Such failures are counted by bounded error type,
reported as mismatches, and rejected by the smoke validator; they are never
treated as equality. Twenty-three focused tests and Ruff pass. The refreshed
source manifest is synchronized to WSL and again verifies 5/5, while the Docker
integration blocker remains unchanged.

The observation-shadow accumulator now serializes complete updates and snapshot
reads with an internal lock, and snapshot dictionaries are detached copies. An
eight-thread, 1,000-operation regression produces exact 400 equivalent, 300
mismatched, and 300 disabled counts; mutating a returned snapshot cannot alter
later evidence. Twenty-four focused tests and Ruff pass. The refreshed source is
synchronized to WSL at 5/5; no Docker-dependent step was retried.

Homework 3 now has a generated eight-family algorithm-scenario-metric matrix
derived from the checked-in draft/pilot YAML and train-only minimal-pair CSV.
All 8/8 families are tied to PGRR components, preserved primary outcomes,
joint-success-only cost metrics, and mechanism diagnostics. The current pairs
remain descriptive development evidence only: they do not establish
superiority, generalization, or significance. Three focused tests, Ruff, and
JSON parsing pass; no Arena, training, frozen test, or final evidence was used.

The eight-family telemetry audit classifies all 20 requested metrics against
the current episode schema: 3 are direct, 14 derivable, 1 both direct and
derivable, and 2 require an operational definition. The unresolved items are
minimum clearance (obstacle versus human clearance) and deadlock duration
(speed/progress/hazard/duration contract). Three focused tests, Ruff, and JSON
parsing pass. This is schema coverage, not evidence that every future run has
already produced every derived metric.

A hash-bound two-anchor diagnosis now compares goal-approach interruption and
lead-pedestrian stop using existing train-only artifacts. Across six recovery
cycles, the diagnostic contract marks the hazard cleared in 6/6 but meaningful
task progress in 0/6. Thirteen of fifteen learned decisions expose only WAIT and
BACKUP in the logged final mask; four completed rejoins still yield no positive
cycle. This localizes the next gate to exact upstream mask tracing, but does not
yet prove which layer is causal. Three focused tests, Ruff, and JSON parsing pass.

Docker WSL integration is restored and the rebuilt ROS overlay completes all
three packages. Two new non-frozen train-only anchor episodes each preserve a
real TIMEOUT with 901 samples. Strict validation finds 162/162 complete mask
traces and no malformed rows or fatal runtime patterns. The observable-scan
layer is the first layer to empty all temporary subgoals in 123/162 decisions;
map connectivity and path corridor are first-empty in 0/162. This localizes a
shared train-only candidate bottleneck but does not establish validation
replication, causality, or performance superiority.

The follow-up observable-scan geometry audit exactly classifies all logged action
removals. Collision-latched decisions are empty in 69/69 cases, 1.4 m candidates
are retained in 0/1134 opportunities, and only three non-empty mask patterns occur.
An approximate replay from saved 180-beam telemetry matches 84.16% of action labels
but only 45.06% of full decisions, so the next gate is diagnostic-only original-scan
predicate telemetry rather than a clearance or policy change.

Diagnostic-only original-scan predicate telemetry is now live and behavior-preserving.
Two fresh train-only anchor runs both preserve TIMEOUT and provide 192/192 valid
traces. All 122 scan-layer empty outputs have no action passing the swept-capsule
predicate even though the directional predicate retains at least one entering action.
The next gate is failure-location telemetry inside the capsule check, not retraining
or lowering the clearance.

Capsule failure-location telemetry is now complete for two new non-frozen train-only
anchor runs. Both preserve TIMEOUT. Across 89 decisions, failed candidates are
blocked at segment interiors or endpoints rather than by initial-overlap handling.
Fifty-five decisions are empty immediately after the scan mask; the other 34 retain
a scan-safe candidate but lose it under downstream directional yield, leaving no
temporary subgoal for the policy in 89/89 decisions. The next gate is an exact
constraint-intersection and scenario-feasibility audit, not threshold tuning or
policy retraining.

Exact downstream reconstruction confirms that all 34 scan-surviving cases contain
only action 2 (0.6 m, -30 degrees), which directional yield removes in 34/34 cases.
The learned selector therefore receives no temporary subgoal in any latest anchor
decision. A static semantic audit also shows that lead-stop is a persistent terminal
blockage without timed release, while goal-approach is a cyclic crossing without an
approach trigger or occlusion. Both remain useful stress prototypes, but new
event-controlled train/validation variants are required before algorithm changes.

An eight-family readiness triage verifies all scenario hashes and preserves all
single-pair outcomes. Base fails in 8/8, PGRR recovery triggers in 7/8, but current
PGRR reaches the goal in 0/8 and only 2/8 configurations have no declared named-event
semantic limitation. Therefore 0/8 is currently ready for core paper comparison.
Work is split into one activation audit, one recovery/feasibility audit, and six
event-semantics/feasibility revisions rather than blindly adding repeats.

A validated non-executable event-control contract now defines replacement train and
validation anchors for bounded lead stopping and one-shot goal-approach crossing. It
requires explicit pre/active/released phases, paired-method fairness, logged release,
post-release path clearance, and zero policy-observation leakage. Four tests pass.
No executable scenario or held-out test was generated; the next gate is a core Python
event-state-machine unit implementation before any ROS connection.

The pure Python event state machine is now implemented under `ramp_core.scenario`.
It enforces far-side arming, one threshold crossing, bounded active duration, explicit
release, monotonic time, and full episode reset for robot-actor or robot-goal distance
triggers. Eight unit tests and Ruff pass. It remains deliberately disconnected from
ROS actor motion and from the recovery-policy observation path; no scenario has been
generated or executed with it yet.

The contract adapter and deterministic offline probe now cover both variants and both
splits. All 4/4 traces arm, trigger once, hold for the configured duration, release,
and remain released. Static source inspection finds no event-core dependency on policy
observation or recovery modules. Twelve combined tests and Ruff pass. This authorizes
only a default-off ROS wiring preflight; actor execution and route feasibility remain
unproven.

The default-off ROS wiring preflight is now complete. All 7/7 prerequisites are
present, while 0/6 runtime-wiring checks are present, confirming that the repository
still preserves the intended offline-only boundary. The report hash-binds the five
source boundaries and fixes seven minimal implementation steps plus post-wiring
acceptance checks. Nineteen related tests pass. No ROS process, simulator, executable
event scenario, policy change, or frozen evaluation was used.

Default-off ROS event-control wiring is now implemented at source level. The actor
controller loads `ramp_event_control` only when explicitly enabled, advances events
only from fresh simulator truth, resets on task/episode boundaries, and publishes
bounded transition telemetry. The episode logger records that telemetry only in the
outcome artifact, and both launchers validate an opt-in 0/1 flag whose default is 0.
Ruff, Python compilation, 38 focused regressions, the 6/6 source preflight, and
normalized-LF shell syntax checks pass. No executable event scenario, ROS build, WSL
runtime sync, or simulator episode has yet been completed.

The first executable-format event candidate is now materialized for train-only
screening. It replaces the permanent lead-pedestrian blockage with one bounded
3 s stop followed by a noncyclic exit through a deliberate far-end opening. The
same hash-pinned JSON is assigned to Base and PGRR, its event mapping parses, its
terminal actor pose clears the route by 3.441 m, and 17 focused tests pass. This is
offline generation evidence only: the ROS overlay has not been rebuilt and no
physical trigger, release, reachability, or method difference has been observed.

The first event candidate has now crossed the WSL build and Base runtime gates.
Nine allowlisted files synchronized with matching hashes and the ROS overlay built
3/3 packages. Base timed out 0.931 m from the goal but logged exactly one activation
at 80.0199 s and one release at 83.5164 s, proving physical event semantics while
also exposing a too-late trigger. The PGRR attempt ended in SIMULATOR_FAILURE before
the event, and its single same-seed retry failed the required-topic startup gate.
No paired claim or core-case promotion is authorized; a known-stable train-only PGRR
control run is required before candidate revision or further retries.

The non-frozen diagonal train control has now produced a valid PGRR TIMEOUT with
893 samples, ruling out a generally broken PGRR runtime. A same-seed lead-stop v2
moved the event earlier and produced a valid pair: Base COLLISION at 220 samples
and PGRR PLANNER_FAILURE (`recovery_sequence_timeout`) at 873 samples. Both methods
logged one activation and release, but Base classified its collision against static
scenario geometry rather than a dynamic human, and PGRR did not reach the goal.
Lead-stop v2 is therefore retained as a negative development result and not promoted;
screening now moves to a less confounded multi-pedestrian closing-gap geometry.

The open-geometry closing-gap candidate completed a valid fixed-seed Base/PGRR pair.
Both methods recorded all four expected actor event transitions, excluding a missed
trigger or startup failure, but both timed out near the goal (2.151 m versus 2.067 m).
Because PGRR did not reach and the pair shows no meaningful method separation, this
candidate is preserved as a negative train-only result and rejected from core-case
promotion without seed search or threshold tuning.

A read-only audit of the frozen 600-episode result found 26 matched conditions where
Base did not reach and PGRR reached, spanning five of the eight final families. A
deterministic descriptive selector now identifies eight qualitative case candidates
while limiting concentration to two per family. These cases are post-hoc illustrations,
not eight independent statistical claims; all formal claims remain based on the full
120 paired conditions and corrected final statistics.

The eight qualitative candidates now have a reproducible evidence-readiness audit.
All 8/8 have complete five-method rows in the frozen results table; 0/8 retain local
scenario JSON plus raw JSONL/sidecars needed for a new trajectory render. One selected
blind-corner pair already has SHA-verified publication trajectory and recovery media.
The safe paper path is therefore an eight-case result table plus that one representative
telemetry figure unless the immutable raw archive can be recovered.

A supervisor-facing post-meeting progress brief now consolidates the interface-layer
work, eight-family train-only pilot, recovery/mask diagnosis, event-controlled negative
results, frozen matched-case evidence, current limitations, and three possible research
routes. It separates completed evidence from open decisions and identifies four items
requiring supervisor direction before any algorithm or new held-out-test expansion.

Supervisor-requirement wording is now corrected: the target is eight independently
defined and repeatably evaluated scenarios, not eight selected episodes. The existing
eight-row frozen shortlist remains useful only as qualitative support for the completed
120-condition result. It does not count toward the new scenario target. Likewise, the
eight train-only extension prototypes do not yet qualify because PGRR reached 0/8 goals.
The current honest completion count for the new eight-scenario objective is therefore
0/8 pending explicit scenario-level promotion criteria and replicated validation.

The first fast-discovery anchor is now a real train-only scenario rather than a prose
design. The medium crossing-flow JSON passes all seven offline geometry/semantics
checks: a static route exists, one temporal conflict is present, post-crossing release
clearance is 6.2 m, and all 21 temporary subgoals are statically available. Its
Base/PGRR runner passes WSL dry-run checks with pinned scenario and checkpoint hashes
and overwrite protection. A real pair was attempted but stopped before either episode
because no Docker client/server or launchable Docker Desktop is currently available.
The anchor therefore remains unpromoted and the new eight-scenario count remains 0/8.

Docker was restored and the exact pinned crossing-flow pair completed. Base collided
with a pedestrian after 272 samples, 14.639 m from the physical goal. PGRR avoided that
collision, entered one recovery cycle, restored the original goal, and reduced the
remaining distance to 3.917 m, but timed out after 900 samples. Because PGRR did not
reach the goal, the anchor is preserved as a valid train-only negative result and is
not advanced to repeats. The new eight-scenario completion count remains 0/8.

A design-corrected 15 m successor to the crossing-flow anchor has now completed its
fixed train-only pair. Only the goal moved from x=26 to x=20; seed, actors, interaction,
90 s horizon, checkpoint, and recovery settings stayed fixed. Base again collided with
a pedestrian at 271 samples, while PGRR entered recovery, used two temporary subgoals,
rejoined and restored the original goal, then reached it at 757 samples with 0.206 m
physical error. This is the first positive single-seed screen (provisional 1/8), not yet
a replicated scenario claim; fully validated new scenarios remain 0/8.

The predeclared crossing-flow v2 train replication gate is now complete. Across seeds
95010/95011/95012, Base collided with a pedestrian in 3/3 paired runs and PGRR entered
recovery/rejoin and reached the goal in 3/3. The r02 PGRR startup first produced a
zero-sample INVALID_RESET; that artifact is preserved and the protocol's sole same-seed
retry produced the valid 710-sample goal reach. The 2-of-3 train gate therefore passes,
making this one train-replicated candidate, not a validation-confirmed or paper-ready
new scenario. The new eight-scenario count remains 0/8 under independent validation.

Crossing-flow v2 has now passed a separately predeclared independent validation gate.
On seeds 96000/96001/96002, Base collided with a pedestrian in 3/3 runs and PGRR
completed recorded recovery/rejoin cycles and reached the original goal in 3/3; all
six episodes were valid first attempts. Geometry, the 15 m route, 90 s timeout,
checkpoint, and thresholds were unchanged after train replication. This is the first
new independently validated scenario (1/8), while remaining only one mechanism with
three validation pairs and therefore not authorizing a general superiority claim.

The user-specified four-scenario priority program is now the canonical extension route:
crossing-flow, goal-approach lateral interruption, bounded closing-gap, and bounded
lead-stop. The second scenario has completed a 15 m fixed-seed screen. Its first Base
startup was a preserved zero-sample SIMULATOR_FAILURE; the sole same-seed retry ended
in dynamic COLLISION at 419 samples, while PGRR observed the one-shot event activate
and release, recovered/rejoined, restored the original goal, and reached it at 663
samples. This candidate advances to train replication only; validated count stays 1/8.

Goal-approach lateral v2 has now passed its predeclared train replication gate. Across
seeds 97100/97101/97102, Base ended in dynamic pedestrian collision in 3/3 paired runs,
while PGRR observed the one-shot activation/release chain, restored the original goal,
and reached it in 3/3. No new infrastructure retries were needed. This remains a
train-replicated candidate until an independently seeded validation gate passes; the
validated scenario count therefore remains 1/8.

Goal-approach lateral v2 has passed its separately predeclared independent validation
gate. On seeds 98100/98101/98102, Base collided with the crossing pedestrian in 3/3
runs, while PGRR completed event activation/release, recovery/rejoin, original-goal
restoration, and goal reaching in 3/3. No valid episode required a retry. The initial
batch script was stopped before r01 simulation by an out-of-range ROS domain and then
resumed with legal domains without changing experiment parameters. This is confirmed
scenario 2/8; frozen test evidence remains untouched.

Bounded closing-gap is now a positive single-seed candidate. The first 15 m/3 s v2
screen kept actors only 1.7 m off route after release; Base collided and PGRR repeatedly
retriggered recovery, timing out 5.72 m from goal. A v3 diagnostic correction changed
only terminal actor clearance to 3.5 m. With the same seed and all other conditions
frozen, Base collided at 414 samples and PGRR completed both event chains, restored the
original goal, and reached at 892 samples. Advance v3 to train replication only; the
independently validated count remains 2/8.

Bounded closing-gap v3 has now completed its predeclared train replication gate and
failed it. Across seeds 98200/98201/98202, Base dynamically collided in 3/3 pairs,
while PGRR reached only in r00 and timed out 2.41 m and 2.01 m from the goal in r01
and r02. Both timeout traces completed actor release and original-goal restoration,
but each contained two recovery cycles whose cycle-level original-goal progress was
nonpositive. The qualifying count is 1/3 against the frozen 2/3 rule. Do not run
independent validation or count this as scenario three; the confirmed count stays 2/8.
