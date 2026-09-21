# Final release decisions

This file records the decisions that define the single supported PGRR release.
Detailed intermediate deliberations remain in Git history and immutable run
manifests; they are not separate maintained product versions.

## D-F01: PGRR is a failure-triggered layer, not a replacement planner

Nav2 DWB controls normal navigation. PGRR activates only for observable
collision risk, freeze, oscillation, deadlock, or planner failure. It selects
one of 21 robot-relative temporary subgoals plus `WAIT`, `BACKUP`, `REPLAN`, or
`CONTINUE`. The classical planner executes temporary goals, and the original
task goal must be restored during rejoin. PPO, continuous learned velocity
control, a learned detector, and a second planner are outside the release
claim.

## D-F02: Keep privileged information in training only

The rollout expert may inspect simulator robot and pedestrian state while
labeling legal actions. Deployed PGRR receives only observable LiDAR, path,
goal, velocity, planner-command, progress, status, and rule-score history.
Privileged fields are written separately and cannot enter test observations.
The selected learner is Uniform BC followed by validation-selected DAgger; the
second DAgger candidate was rejected on validation.

## D-F03: Use one bounded, fail-closed recovery state machine

The action mask removes unsafe, occupied, disconnected, occluded, or
unavailable actions and always retains a safe fallback. The system stores the
original goal, runs bounded recovery, requires stable clearance and at least
0.25 m original-goal progress before resetting the recurrence budget, completes
a post-retreat turn before release, and rejoins Nav2. Emergency stopping remains
independent of policy output. These are empirical safety mechanisms, not a
formal collision-free guarantee.

## D-F04: Separate ROS runtime and offline analysis environments

Online execution uses the pinned Ubuntu 22.04 / ROS2 Humble / Arena Gazebo
profile with Jackal, Nav2 DWB, planar LiDAR, Xvfb, and software rendering.
Offline data, learning, statistics, figures, and tests use the Python 3.10
`ramp-offline` Conda environment. Runtime helpers remove Conda and foreign ROS
variables; offline helpers never source ROS. The deterministic cylindrical
pedestrian proxies are simulator actors, not a validated human-intent model.

## D-F05: Freeze one benchmark identity and preserve its hashes

The public product has one release. Its internal benchmark ID is
`moderate_social_navigation_v6`, retained because it is embedded in scenario
IDs, split hashes, results, and the 96-file artifact manifest. Renaming that ID
after evaluation would break provenance; the suffix is therefore an immutable
dataset identifier rather than a user-facing version choice.

The final benchmark contains eight interaction families, three densities, and
five held-out repeats: 120 shared conditions per method and 600 logical
method--episodes over Base, Standard, Heuristic, Uniform BC, and PGRR. Train,
validation, and test use disjoint scenario IDs and seed blocks. The accepted
calibration report is fixed by SHA-256 in the final configuration.

## D-F06: Reject a calibration before test rather than relax its threshold

One earlier validation candidate let Base reach 57/72 goals (79.17%), above
the preregistered 75% ceiling. Its test was never opened. The final benchmark
retained its geometry, changed only the Crossing Flow timing band from
validation evidence, used fresh seeds, and passed the unchanged calibration.
This history remains in the paper because it demonstrates that the test was
not used for benchmark tuning; it is not presented as another current release.

## D-F07: Keep algorithm outcomes and infrastructure attempts distinct

`GOAL_REACHED`, `COLLISION`, `TIMEOUT`, and `PLANNER_FAILURE` are final
algorithm outcomes and are never retried. Only classified
`SIMULATOR_FAILURE` or `INVALID_RESET` attempts may be retried, at most twice,
and every physical attempt remains in provenance. A logical result is accepted
only when the final run manifest is complete and the collector can bind the
terminal artifact to its task and scenario hashes.

The final record contains 600 algorithm outcomes, eight excluded simulator
failures, six excluded invalid resets, and 42 no-outcome command records over
39 unique tasks. Resumes recovered only incomplete tasks.

## D-F08: Use paired tests and one global multiple-comparison correction

All methods share the same 120 condition keys. Goal, collision, and timeout
comparisons use exact paired tests; every preregistered hypothesis across
methods and endpoints enters one Holm family. `PLANNER_FAILURE` is reported as
a separate descriptive terminal class because it was not a preregistered
binary inferential endpoint. Duration and path length use only joint-success
pairs and must state that conditioning explicitly.

## D-F09: Bound the scientific claim to the observed trade-offs

PGRR versus Base improves goal reaching by 20.00 percentage points and reduces
collision by 29.17 points, both significant after global Holm correction. It
also takes 15.88 s longer and travels 1.89 m farther on 83 joint successes,
with higher angular jerk. The preregistered goal/collision/timeout comparisons
against Heuristic and Uniform BC do not establish general superiority after
correction; planner failure remains descriptive. The release claims a Base-DWB
safety and completion improvement with efficiency/smoothness costs, not better
comfort, formal safety, universal superiority, unseen-map generalization, or
hardware readiness.

## D-F10: Bind publication claims to checked-in evidence

Every paper number is generated from the final Parquet/JSON/CSV bundle. The
anonymous paper must be exactly 8 pages, the Chinese report exactly 32 pages,
and the presentation exactly 30 slides/pages. The release manifest binds 96
artifacts, document page counts, the evaluation commit, the generation commit,
and media hashes. Release mode runs only from a clean worktree and validates
without regenerating files.

The real Gazebo GUI image is labeled as a historical moderate-v5 validation
environment capture (benchmark provenance, not another current release); it is
not called a camera frame from the held-out statistical run. The same-condition
Base--PGRR trajectory and recovery timeline are real telemetry reconstructions
and are not called screenshots.

## D-F11: Preserve one historical boundary without pooling it

The earlier frozen 64/64 audit remains visible because it prevents selective
reporting: PGRR/Base collisions were 0/24 versus 19/24, timeouts were 16/24
versus 0/24, and goal reaches were 8/24 versus 5/24; the adjusted goal-reaching
comparison was not significant. Those rows are not pooled with, copied into,
or used to tune the final benchmark.

## D-F12: Publish the same release state on `main` and `home`

`main` is the canonical integration branch and `home` is the synchronized
working mirror requested for this project. A release is complete only when the
same final project commit is reachable from both remote branches and a clean
checkout passes the release validator.

## D-S01: Prototype cycle-level progress assessment outside the frozen runtime

The eight-family train-only diagnostic shows that successful rejoin transitions
often do not produce original-goal progress. A pure `ramp_core` assessment
interface therefore checks original-goal activation, observable hazard
clearance, task progress, and rapid retrigger as separate signals. It has no
default thresholds and is not connected to ROS or the release state machine.
Threshold selection and runtime integration require a new train/validation
development protocol; the frozen test and release behavior remain unchanged.

## D-S02: Treat absent retrigger evidence as censored when observation is short

The offline cycle adapter records both a retrigger delay and the available
post-rejoin observation duration. A missing retrigger is accepted as stable
only when the full explicit window was observed; cycles ending near episode
termination are marked incomplete. The first probe mirrors existing runtime
scales for interpretation only and is not a new threshold selection or runtime
configuration.

## D-S03: Test the action-mask chain before changing the learned checkpoint

In the train-only eight-family traces, 50/58 learned events with parseable
final masks permit only WAIT/BACKUP. When an alternative remains, the policy
splits four WAIT/BACKUP versus four temporary-subgoal choices. This evidence
prioritizes an offline mask-chain ablation before retraining or changing the
selected model. Emergency guards remain safety authority and must not be
relaxed merely to improve completion.

## D-S04: Trace upstream candidate construction before changing late mask rules

Logged mask transitions show that 46/50 final WAIT/BACKUP-only learned events
are already restricted before the first recorded `bc_yield_mask` step. Only
three final collapses are attributable to `bc_closing_side` and one to
`bc_yield_mask` in the recorded chain. Therefore the next safe investigation
is a static call-order map and synthetic replay of base candidate construction
and earlier safety filtering. No mask is relaxed and no runtime, checkpoint,
or frozen-test behavior changes on the strength of this observational result.

## D-S05: Replay map, scan, and corridor masks independently before ablation

The verified runtime call order shows that only map/connectivity masking,
observable LiDAR masking, and path-corridor masking can remove temporary
subgoals before the first logged yield transition. Rejoin filtering affects
only CONTINUE/REPLAN. The next development artifact will therefore replay
these three pure-Python stages independently on synthetic inputs. Runtime
telemetry changes or rule relaxation are deferred until that fixture explains
the geometric failure boundary.
## D-S06: Label retrospective scan/corridor replay as approximate

All 60 existing learned-decision records contain pose, 180-bin resampled LiDAR,
and a global path, but none contains the original LaserScan geometry, occupancy
map snapshot, latched task-corridor path, or runtime mask-parameter snapshot.
Retrospective scan/corridor replay may be used only as an explicitly approximate
diagnostic. Exact layer attribution requires new train/validation telemetry;
it cannot be inferred from these logs or applied to the frozen benchmark.
## D-S07: Prioritize per-layer telemetry, not safety-rule relaxation

Approximate replay reproduces 27/46 logged empty temporary-subgoal sets, with
26 becoming empty at the reconstructed scan layer. However, 19 remain
unexplained and five events show approximation-induced false elimination.
Future train-only diagnostics should therefore record per-layer retained action
IDs while leaving mask computation untouched. This evidence does not authorize
relaxing LiDAR clearance, path bounds, or any frozen-release behavior.
## D-S08: Gate future mask telemetry on behavioral equivalence

The proposed `MaskTraceRecorder` remains outside ROS and defaults disabled.
Any future train-only integration must prove that both disabled and enabled
diagnostics preserve the final action mask and selected action; enabled mode
may add telemetry only. Stage continuity and undeclared reauthorization are
treated as errors. No diagnostic integration is permitted in the frozen
release configuration.
## D-S09: Limit the first integration proposal to three upstream stages

The trace-on/off equivalence fixture passes for open, enclosed-map, close-scan,
and narrow-corridor inputs. A future minimal ROS patch should therefore trace
only map/connectivity, observable scan, and path corridor, default disabled.
Later constraints remain out of the first patch so behavioral equivalence and
telemetry size can be reviewed before expanding coverage.

## D-S10: Keep integrated upstream telemetry opt-in and outside special-action authorization

The first ROS integration records only map/connectivity, observable scan, and
path corridor, and the controlling parameter defaults false. The trace ends
before REPLAN, WAIT, and CONTINUE availability is finalized, because the current
diagnostic question concerns loss of the 21 temporary subgoals. Enabled mode may
append the observed transitions to the decision reason but must preserve action
ID and confidence. Live validation is restricted to a non-frozen train-only
smoke before any broader use.

## D-S11: Require a checked train-only preflight before live trace smoke

The opt-in trace smoke must reject non-train splits, frozen path markers, and
existing episode IDs before invoking Arena. A successful preflight establishes
only that the requested inputs and launch contract are safe; it is not a
simulator result. If Docker/WSL integration or the synchronized runtime mirror
is unavailable, record that environment blocker and do not fabricate or replace
the episode.

## D-S12: Treat live mask tracing as diagnostic evidence, not method performance

The first valid live trace episode must retain its actual terminal outcome and
all failed setup attempts. A completed wrapper with outcome TIMEOUT validates
the telemetry path but not navigation success. Each traced decision must contain
the map/connectivity, observable-scan, and path-corridor records exactly once in
that order, and known recovery-manager import or parameter failures invalidate
the trace. Normal Arena shutdown exceptions are reported separately rather than
silently discarded. This gate authorizes read-only layer statistics on new
train/validation data, not threshold tuning or frozen-test use.

## D-S13: Replicate direct layer attribution before changing any mask rule

The first live trace localizes temporary-subgoal elimination to observable scan
(first empty in 85/110 decisions) and path corridor (25/110), with zero removal
at map/connectivity. Because this is one TIMEOUT episode, the next gate is a
small non-frozen train/validation replication with unchanged parameters. No
safety distance, corridor bound, model, or action threshold may be changed on
the strength of this single episode.

## D-S14: Require trigger coverage before cross-split mask attribution

Two different train scenarios reproduce upstream temporary-subgoal elimination,
but neither attempted validation seed triggers recovery. A zero-trace episode
with a clean runtime is classified as `not_triggered`, not as telemetry failure
and not as evidence against the mask hypothesis. Before any validation-layer
comparison, diagnose whether the interaction is non-threatening or the existing
detector misses it. Do not tune the detector or mask thresholds on these few
validation episodes, and do not accumulate blind retries.

## D-S15: Separate detector-negative, selector recovery, and emergency-only episodes

A missing temporary-subgoal trace is not synonymous with a NORMAL episode.
Trigger-coverage reports must separately identify selector recovery states
1--3 and emergency stop state 4. Privileged robot-human distance may be reported
only as a diagnostic proxy and never as a policy input or proof of safety. The
next validation smoke must be chosen by a preflighted selector-coverage criterion
with thresholds fixed; emergency-only and zero-score episodes remain preserved.

## D-S16: Use same-family selector evidence for the next validation smoke

Choose the lead-stop validation prototype before any additional diagonal or
head-on retry: its train counterpart already demonstrated selector recovery,
whereas diagonal is detector-negative and head-on validation is emergency-only.
Generation must use the catalog validation seed and an explicit validation
split, forbid held-out test material, and pass the default-off trace preflight.
This is a cross-seed development replication, not a generalization claim.

## D-S17: Freeze a structural snapshot before the first Homework 2 extraction

Record the recovery-manager source hash, method spans, and internal calls before
moving code. The observation/geometry seam is the preferred first candidate
because its 9 methods span 95 lines, while mask/policy selection spans 426 lines
and includes the 233-line `_select_decision`. Static size is not proof of low
semantic risk, so characterization fixtures remain mandatory before extraction.

## D-S18: Generate extension prose only through an evidence-to-claim ledger

Every numerical extension statement must be generated from its listed checked-
in CSV/JSON and paired with an explicit forbidden inference. Train-only pair
outcomes may describe a safety/completion tradeoff but not superiority; mask
traces may describe layer behavior but not causality; static preflight may not
be written as runtime evidence. Keep this ledger separate from the frozen final
release and formal paper until a locked experiment gate authorizes inclusion.

## D-S19: Build the observation module before rewiring the ROS node

Introduce a stateless, deployable-only `RecoveryObservationBuilder` that exactly
records the existing shaping contract, but leave the node on its old inline
implementation until a dual-path characterization fixture proves field-level
equivalence. The interface must reject empty LiDAR history and expose no
privileged-human input. No threshold, model, state-machine, or execution logic
belongs in this first module.

## D-S20: Require exact offline observation equivalence before shadow wiring

Use a seeded characterization probe spanning path fallback, LiDAR padding and
history truncation to compare the inline reference and builder field by field.
Zero error on these pure inputs permits preparation of a default-off runtime
shadow comparison, but does not authorize replacing the live node path: ROS
callback and goal-lifecycle timing still require non-frozen validation.

## D-S21: Do not label the later DAgger result as overfitting from epoch curves alone

Audit expert-label and action-mask distributions before attributing validation
behavior to model overfit. The manifest-matching later train set is WAIT-heavy
and much more tightly masked, which is a competing coverage/label explanation.
A strict selected-vs-later comparison remains blocked until the selected train
and shared validation HDF5 match their recorded manifest hashes.

## D-S22: Preserve unresolved DAgger hashes rather than repairing manifests post hoc

If a manifest-pinned HDF5 hash is absent from both local storage and Git history,
do not rename a different file or update the manifest to make the check pass.
Mark canonical comparison unavailable and request a trusted external copy only
when that comparison becomes necessary. Continue independent work that does not
depend on those missing bytes.

## D-S23: Separate selector-path replication from navigation performance

A non-frozen validation episode may close the cross-split telemetry gate when it
contains complete ordered selector-layer traces, even if its preserved outcome
is TIMEOUT. Treat that as evidence that the diagnostic path is observable across
splits, not as navigation success, generalization, superiority, or permission to
tune thresholds. Performance claims still require the locked experiment gate.

## D-S24: Diagnose the timeout before proposing algorithm changes

Treat per-cycle original-goal progress, travelled distance, final observable
action set, and selected action as separate evidence. The current validation
TIMEOUT shows repeated nonprogress cycles and a WAIT/BACKUP/REPLAN-only action
pattern, but one episode cannot identify which component caused the failure.
Do not alter directional-yield, mask, detector, or policy thresholds from this
trace; first prepare a non-frozen controlled comparison with a preregistered
diagnostic question.

## D-S25: Shadow the observation builder lazily and default off

Any future runtime comparison must leave the existing inline observation as the
authoritative input. The candidate builder is evaluated only when an explicit
diagnostic switch is enabled, and discrepancies are reported rather than used
to change actions. This permits non-frozen runtime characterization without
silently altering normal behavior or frozen evidence.

## D-S26: Aggregate shadow evidence without retaining observations

Future runtime shadow telemetry must use constant-memory counters and field-wise
maximum errors rather than storing full observation arrays per sample. This
limits diagnostic overhead and avoids creating a second raw sensor dataset. The
aggregate remains non-authoritative and must not affect actions or state changes.

## D-S27: Require input ownership before enabling a shadow candidate

A diagnostic candidate must not alias or freeze mutable buffers owned by the
authoritative controller. Copy `base_action` at the builder boundary and retain
regression coverage proving source arrays remain writable and independent. This
ownership gate must pass before any default-off ROS integration is attempted.

## D-S28: Keep the legacy observation authoritative during ROS shadow wiring

The ROS node may construct the candidate observation only behind a default-false
parameter, but it must always return the legacy inline object. Comparison output
is diagnostic aggregate state and cannot feed policy, masks, state transitions,
or commands. Preserve the pre-wiring structural snapshot separately from each
post-wiring characterization.

## D-S29: Enable observation shadow only through the standard guarded launcher

The supported runtime enable path is `RAMP_ENABLE_OBSERVATION_SHADOW=1` through
the standard Arena wrapper. The wrapper must default to `0`, reject values other
than `0/1`, and the inner launcher must convert the value to a ROS boolean. Every
enabled run requires a fresh preflighted train or validation episode ID; frozen
paths and test scenarios are prohibited. This diagnostic switch cannot change
the legacy observation's authority.

## D-S30: Separate observation equivalence from navigation outcome

The shadow smoke passes only when its single teardown summary contains at least
one comparison, zero mismatches, zero stored per-sample observations, and an
unchanged authoritative path. Preserve the actual episode outcome separately;
collision, timeout, or goal reaching cannot by itself prove or disprove builder
equivalence and must not be converted into a performance claim at this gate.

## D-S31: Pin and verify the five runtime sources before rebuilding

The diagnostic smoke may proceed only when the WSL runtime checkout matches the
preflight line-ending-normalized SHA-256 values for the observation builder, shadow comparator, ROS
node, and both launch wrappers. Verification is read-only. If synchronization
is needed, inspect the target worktree first and copy only those explicit files;
never replace a directory or overwrite unknown target changes implicitly.

## D-S32: Synchronize cross-platform runtime files through an allowlist

Do not use ad-hoc shell line-ending substitutions for runtime synchronization.
Use the tested five-path synchronizer, require the preflight hashes to match the
source before writing, back up every existing target, normalize output to LF,
and verify target hashes afterward. Any mismatch stops before build or runtime.

## D-S33: Contain diagnostic candidate exceptions but fail the evidence gate

An enabled shadow candidate may catch ordinary `Exception` values arising only
inside candidate construction or comparison so that the legacy observation can
remain authoritative. Record a bounded exception type and count, mark the
comparison unequal, and require the runtime validator to reject the smoke.
Never catch process-control exceptions or reinterpret candidate failure as
equivalence.

## D-S34: Make diagnostic aggregation atomic and snapshots detached

Even though the current entry point uses the default executor, the shadow
accumulator must not assume single-threaded callbacks. Protect complete record
updates and summary reads with one lock, and return copies of nested mutable
maps. Keep the lock outside the authoritative observation path when shadowing is
disabled and retain zero per-sample storage.

## D-S35: Separate outcome, cost, and mechanism evidence in the eight-family study

Report GOAL_REACHED, COLLISION, and TIMEOUT for every preserved episode. Compare
completion time, path length, and angular jerk only on joint successes so that
failures are not silently converted into favorable efficiency values. Use
trigger, recovery-cycle, action-switch, temporary-subgoal, REPLAN, and
goal-restore fields as mechanism diagnostics, not as proof of causality. The
current single train-only pair per family is development evidence and cannot
support superiority, generalization, or significance claims.

## D-S36: Freeze ambiguous metric definitions before comparative runs

Do not use a generic `minimum_clearance_m` without declaring whether it refers
to all sensed obstacles, privileged human distance, or two separately reported
metrics. Do not compute `deadlock_duration_s` until the speed threshold,
progress window, hazard condition, and minimum duration are fixed. Select and
record these definitions using train/validation reasoning only, then keep them
unchanged for held-out evaluation. Existing telemetry inputs do not authorize
post-result metric selection.

## D-S37: Require exact mask-layer evidence before the anchor algorithm change

Treat the two-anchor final-mask result as localization, not causal attribution.
The next runtime gate is one non-frozen full-layer mask trace per anchor. Do not
retrain the policy, relax safety thresholds, or change candidate filtering until
the first exact layer removing temporary subgoals is identified. A completed
rejoin is not a successful recovery unless it also produces preregistered task
progress and preserves the original goal.

## D-S38: Investigate observable-scan candidate removal before retraining

The exact two-anchor runtime trace supersedes the earlier final-mask-only
localization for the next development gate. `observable_scan` is first to empty
all temporary subgoals in 123/162 decisions, while map and path layers are
first-empty in none. Audit this layer's geometry and replay behavior before any
policy retraining or safety-threshold change. Any later modification must remain
general across both anchors, preserve collision safety, and be selected on
train/validation only.

## D-S39: Require original-scan predicate telemetry before changing clearance

The exact trace shows a structural candidate bottleneck: all 69 collision-latched
decisions have no temporary subgoal, every 1.4 m candidate is removed, and only
three non-empty masks occur across 162 decisions. However, replay from the saved
180-beam scan matches only 84.16% of per-action labels and 45.06% of complete
decisions because runtime masking uses the original LaserScan. Add diagnostic-only
runtime telemetry for directional and swept-capsule predicate outcomes before
attributing removals or changing the 0.90 m collision-latched clearance.

## D-S40: Localize capsule failures before proposing a safety change

Original-LaserScan telemetry reproduces the observable-scan mask in 192/192
decisions. Every one of the 122 empty scan outputs has no entering action passing
the swept-capsule predicate, while the directional predicate still has at least
one entering action. Treat the capsule check as the direct shared bottleneck on
these two train anchors, not as proof that its clearance is excessive. Record
minimum segment clearance and whether failure is initial, intermediate, or endpoint
before designing a general candidate correction; preserve current thresholds meanwhile.

## D-S41: Treat the anchor failure as a constraint-intersection problem

The latest exact two-anchor trace contains 89 recovery decisions. Capsule
failures occur at segment interiors and endpoints, not in the initial-overlap
categories, so do not broaden the initial-overlap exemption. Fifty-five decisions
lose all temporary subgoals at the scan layer; the remaining 34 retain a scan-safe
candidate but lose it under the downstream directional-yield constraint. No
decision presents a temporary subgoal to the learned selector. Diagnose the exact
constraint intersection and scenario feasibility before changing clearance,
directional-yield bounds, candidate geometry, or policy training.

## D-S42: Preserve the two anchors as stress tests, not complete named events

The lead-stop prototype terminates its actor route on the robot path without an
explicit stop trigger or bounded release. The goal-approach prototype is a cyclic
crossing without robot-approach synchronization or occlusion. Preserve their files,
runs, and failure outcomes as train-only stress diagnostics, but do not use them as
complete evidence for the named causal events or tune safety parameters to make them
pass. Build separate event-controlled train/validation variants and verify event
occurrence, release, and task feasibility before comparative evaluation.

## D-S43: Gate eight-family promotion instead of multiplying repeats

All eight hash-pinned train-only pairs expose a Base failure, but PGRR reaches the
goal in none of the eight current development runs. Seven families trigger recovery;
only two current configurations carry no declared named-event semantic limitation.
Preserve all eight as stress diagnostics, but do not expand repeats or comparators
uniformly. Route the no-trigger family to activation diagnosis, the semantically
complete triggered family to feasibility/recovery diagnosis, and the other six to
event-semantics and task-feasibility work. Require train success and then validation
replication before promotion into a core comparative set.

## D-S44: Freeze event semantics before implementing runtime control

Use a three-phase `pre_event -> active_event -> released` contract for the two
replacement anchor variants. Require one logged trigger, bounded active duration,
logged release, an off-path terminal actor pose, a collision-free post-release route,
identical paired-method event contracts, and no event-controller state in policy
observations. Keep the contract train/validation-only and non-executable until a core
Python event state machine passes unit tests. Do not materialize held-out test cases,
change recovery thresholds, or enable an occlusion claim at this gate.

## D-S45: Keep event control outside the recovery-policy observation path

Implement the event contract first as a pure `ramp_core.scenario` state machine.
Require a far-side arming observation before the one-shot threshold crossing, enforce
monotonic simulation time, bounded active duration, explicit release, and reset of
all episode state. Support only robot-actor and robot-goal distance triggers at this
gate. Do not import the recovery observation schema, connect ROS, or alter actor
motion until the configuration adapter and deterministic trace probe pass offline.

## D-S46: Require an offline contract trace before ROS event wiring

Adapt each train/validation variant into the same core state-machine type and require
the deterministic probe to produce exactly one pre-to-active and one active-to-release
transition. Keep split-specific seeds, trigger distances, and durations explicit.
Statically reject dependencies from the event core to policy observation or recovery
modules. The successful four-trace probe authorizes only a default-off ROS wiring
preflight, not executable scenarios, parameter tuning, or comparative runs.

## D-S47: Wire event control only behind a default-off runtime gate

The source inventory confirms 7/7 prerequisites and no existing event runtime wiring.
Implement the seven preflighted changes in order, with `enable_event_control=false` as
the authority-preserving default. Event advancement must occur only with fresh actual
robot pose; task reset must reset every state machine; invalid configuration or stale
pose must fail closed; transition telemetry may be logged but must not enter recovery
observations. Prove the unset path remains behaviorally unchanged before WSL sync,
overlay build, or any non-frozen train-only simulator smoke.

## D-S48: Treat source wiring as a gate, not simulator evidence

The default-off source wiring now passes its static and unit gates. Keep the event flag
at zero for all legacy and frozen workflows. Before any ROS build or Arena execution,
materialize only the two declared train-only anchor variants and reject any scenario
whose controlled actor is cyclic, whose terminal waypoint remains on the robot path,
or whose Base/PGRR paired contract differs. A 6/6 wiring report does not establish
physical trigger timing, release behavior, route feasibility, or method performance.

## D-S49: Screen one fixed-seed event candidate before multiplying scenarios

Use the bounded lead-stop train candidate as the first end-to-end event-control gate.
Base and PGRR must receive the identical hash-pinned JSON; the event must activate
once, release after 3 s, and leave a physically feasible route. Run one fixed seed
per method before considering repeats. Preserve any negative result and diagnose it;
do not search seeds, materialize test cases, tune recovery thresholds, or call an
offline preview a simulator result. Only after a PGRR goal and a dynamic-human Base
failure may the mechanism advance to validation replication.

## D-S50: Diagnose runtime validity before interpreting the first event pair

Treat the Base event trace as event-semantics evidence only. Because neither PGRR
attempt formed a valid episode, the pair says nothing about comparative performance.
Do not keep retrying or alter the seed. Run one historically stable, non-frozen
train-only PGRR control scenario first. If that control is invalid, repair the runtime;
if it is valid, revise the candidate's late event timing under the same fixed-seed
screening discipline. In neither case may this candidate enter the eight core scenarios
until a valid paired run and validation replication exist.

## D-S51: Reject mechanism-confounded lead-stop v2 and move on

The valid v2 pair does not meet the core-case contract. Base collision is attributed
to static scenario geometry, not the controlled pedestrian, and PGRR ends in
recovery_sequence_timeout. Preserve both outcomes as a negative development result.
Do not search seeds, reduce recovery thresholds, or repeatedly reshape the narrow
walls around this example. Screen the next distinct mechanism in open geometry so a
Base failure can be attributed to dynamic pedestrians and require a PGRR goal before
promotion.

## D-S52: Reject the valid but non-separating open closing-gap pair

Accept the four recorded event transitions as proof that the open closing-gap runtime
semantics work. Do not promote the candidate because Base and PGRR both time out near
the goal and PGRR does not reach it. Preserve the fixed-seed artifacts, do not retune
the candidate or search seeds, and screen a genuinely different train-only interaction
mechanism next. A core case still requires a valid paired Base failure and PGRR goal
before validation replication.

## D-S53: Use frozen matched results for eight qualitative cases, not eight claims

Use the completed 120-condition final evaluation as the authoritative source for
illustrative cases rather than repeatedly reshaping new train scenarios after observing
outcomes. Select cases reproducibly from Base-non-goal/PGRR-goal pairs, cover every
eligible family, and cap concentration at two per family when possible. Label the eight
rows as post-hoc qualitative examples spanning five mechanisms. Keep inferential claims
on the complete preregistered data and corrected statistics; do not imply that eight
distinct mechanism families show superiority.

## D-S54: Separate case-table readiness from trajectory-render readiness

Treat complete, hash-bound rows in frozen `results.parquet` as sufficient for the
eight-case descriptive table. Require the original JSONL plus metadata/outcome
sidecars before rendering any new trajectory. Use the one already SHA-verified matched
trajectory and recovery timeline as the representative figure. Missing raw archives
must be reported as an evidence-availability limitation, never repaired by rerunning
the frozen test or by reconstructing unrecorded motion.

## D-S55: Professor requirement is eight reproducible scenarios, not eight episodes

Supersede any wording that treats the deterministic eight-row frozen shortlist as
completion of the supervisor's requirement. The required unit is a separately defined,
repeatable scenario evaluated by a predeclared paired protocol and showing a stable PGRR
advantage over Base; an isolated Base-fail/PGRR-goal episode is only qualitative support.
Retain the eight frozen rows as post-hoc examples for explaining the existing 120-pair
result, but report current completion of the new eight-scenario objective as zero until
scenario-level promotion criteria are defined and passed. The eight train-only extension
prototypes also do not qualify because PGRR reached the goal in 0/8 initial pairs.

## D-S56: Begin fast discovery with one hash-pinned crossing-flow anchor

Use the frozen crossing-flow/medium aggregate only as a development prior, not as data
to pool with the new experiment. Screen the new seed-95010 train scenario first with
one identical Base/PGRR pair. Advance to three train repeats only if Base fails and
PGRR reaches; otherwise preserve the negative result and move to another mechanism.
The current Docker outage is an environment blocker, not authorization to alter the
seed, policy checkpoint, recovery thresholds, frozen benchmark, or promotion rule.

## D-S57: Reject the first crossing-flow anchor after its fixed pair

Preserve the seed-95010 pair as a valid development result: Base collided early while
PGRR avoided collision and restored the task goal, but PGRR timed out rather than
reaching it. The scene therefore fails the minimum positive promotion gate. Do not run
additional seeds, lengthen the 90 s episode, tune thresholds, or reshape this anchor.
Move to the next distinct mechanism so discovery time is spent on breadth rather than
post-hoc optimization of one negative case.

## D-S58: Advance the 15 m crossing-flow v2 to replication, not publication

The user's route-length constraint and the later eight-family audit establish a general
task-horizon design correction, superseding D-S57's decision to abandon this mechanism.
Accept the v2 single pair as a positive screen because only the goal changed, Base
reproduced its pedestrian collision, and PGRR recovered, restored the original goal,
and reached it. Freeze the v2 geometry, 90 s timeout, checkpoint, and thresholds now.
Predeclare two additional train seeds and require at least 2/3 Base-fail/PGRR-goal pairs
before independent validation. Until then, report one provisional candidate and zero
fully validated new scenarios.

## D-S59: Freeze crossing-flow v2 after passing the train replication gate

Accept the three predeclared train pairs as a passed replication gate: Base collided
and PGRR reached for seeds 95010, 95011, and 95012. Preserve the r02 zero-sample
INVALID_RESET separately and accept only its one same-seed retry as the selected valid
episode. Freeze the scenario geometry, 90 s timeout, checkpoint, thresholds, and train
evidence now. Before any further run, predeclare independent validation seeds and the
validation promotion rule. Do not tune from those results, use the locked moderate_v6
test, or count this train-replicated candidate as one of eight fully validated scenarios.

## D-S60: Promote crossing-flow v2 as scenario 1/8 and close its design loop

Accept the predeclared validation result (3/3 Base collision and PGRR goal reach) as
independent confirmation of one new scenario. Count crossing-flow v2 as 1/8 under the
supervisor's scenario objective, while retaining the six train/validation pairs as
descriptive scenario-level evidence rather than a stand-alone significance claim.
Freeze this design permanently: do not add seeds, modify geometry, change timeout or
thresholds, or rerun it on the locked moderate_v6 test. Move discovery to a distinct
interaction mechanism so the remaining seven scenarios add breadth rather than variants
of the same crossing-flow case.

## D-S61: Use the corrected four-scenario priority program and advance scenario two

Supersede the mistaken temporary-blockage/head-on ordering with the user's four fixed
optimization targets: crossing-flow medium, goal-approach lateral interruption,
bounded closing-gap, and bounded lead-stop. Accept goal-approach v2 as a positive
single-seed screen because Base dynamically collided while PGRR observed one activation
and release, recovered/rejoined, restored the goal, and reached it. Freeze this v2
geometry and event contract, predeclare two additional train seeds, and require the
same 2-of-3 gate used for crossing-flow before independent validation. Preserve the
zero-sample Base infrastructure failure and its sole same-seed retry.

## D-S62: Freeze goal-approach v2 after a 3/3 train replication pass

Accept seeds 97100/97101/97102 as the complete train gate: Base collided dynamically
in all three pairs, and PGRR reached after a complete event chain and original-goal
restoration in all three. Freeze geometry, event timing, 15 m route, 90 s timeout,
checkpoint, thresholds, and train evidence. The next admissible step is a separately
predeclared independent validation set; do not tune from it or touch moderate_v6.

## D-S63: Promote goal-approach v2 as confirmed scenario 2/8

Accept the terminal independent-validation result: all three new seeds produced Base
dynamic collision and PGRR goal reach, with complete event and original-goal-restoration
evidence. Freeze and close this design; do not add favorable seeds or reshape it.
Count it as scenario 2/8 and move optimization to bounded multi-pedestrian closing-gap.
Treat the corrected pre-launch ROS-domain error as runner configuration history, not an
episode outcome, because no simulator episode or outcome artifact was created.

## D-S64: Advance bounded closing-gap v3 to train replication

Reject v2 because its 1.7 m terminal actor clearance caused repeated post-release
recovery and a timeout still 5.72 m from goal. Accept v3's terminal-clearance correction
as mechanism-preserving: all interaction timing, route, seed, model, timeout, and
thresholds remained fixed. Its Base collision/PGRR goal reach plus complete two-actor
event and goal-restoration evidence pass the single-seed screen. Freeze v3 now and use
a predeclared 2-of-3 train gate before any independent validation.

## D-S65: Reject bounded closing-gap v3 after train replication

Accept the complete predeclared train result rather than the favorable r00 screen:
Base collided dynamically in 3/3 pairs, but PGRR reached in only 1/3 and timed out in
r01/r02. Both timeouts retained complete release and goal-restoration evidence, so they
are valid algorithm/scene outcomes rather than infrastructure failures. Close v3 at
the failed train gate, preserve every episode, do not replace seeds or alter the 90 s
horizon after inspection, and do not spend independent-validation budget on it. The
confirmed new-scenario count remains 2/8.
