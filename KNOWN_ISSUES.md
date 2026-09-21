# Known issues and release limitations

There are no open blockers for the frozen PGRR release. This file lists the
limitations that remain scientifically or operationally relevant. Resolved
development incidents are preserved in Git history and run manifests rather
than presented as current project variants.

## KI-F01: The gain over Base carries efficiency and smoothness costs

PGRR improves goal reaching by 20.00 percentage points and reduces collision by
29.17 points relative to Base DWB; both paired comparisons remain significant
after global Holm correction. It still records two timeouts and nine planner
failures. On the 83 joint-success pairs, it takes 15.88 s longer and travels
1.89 m farther, with higher angular jerk. Its observed personal-space violation
ratio is 4.13 points higher, although that comparison is not significant after
global correction.

Observed differences against Heuristic and Uniform BC on the three
preregistered terminal endpoints (goal, collision, and timeout) are not
significant after global correction; planner failure remains descriptive. The
result does not support universal superiority, better comfort, or a formal
safety claim.

## KI-F02: Planner failure remains a completion bottleneck

PGRR terminates with nine `PLANNER_FAILURE` outcomes versus none for Base.
Planner failure was not a preregistered binary inferential endpoint, so the
7.50-point marginal difference is descriptive and receives no post-hoc
significance test. Future work should reduce planner aborts without tuning on
the existing held-out test.

## KI-F03: The fallback map omits some physical shelf geometry

The Arena `map_empty` occupancy map does not include every shelf used to create
the physical interaction corridor. The observable safety layer and
scenario-aware checks compensate empirically, but Nav2 can still propose a
route through geometry that Gazebo treats as occupied. This contributes to
blind-corner and rejoin difficulty and prevents a formal map-consistency claim.

## KI-F04: Dynamic agents are deterministic proxies, not validated humans

The pinned Arena Humble fallback uses seeded LiDAR-visible cylindrical
pedestrian proxies with deterministic routes. They provide reproducible dynamic
interactions but do not model human intent or establish social acceptability.
The release has no human-subject, hardware, cross-simulator, unseen-map,
second-planner, or formal-safety validation.

## KI-F05: Gazebo startup required auditable retries

Six-worker execution completed every logical task, but the retained provenance
contains eight `SIMULATOR_FAILURE` and six `INVALID_RESET` physical attempts.
Attempt snapshots also contain 42 launch commands without outcome files over 39
unique tasks. Only incomplete infrastructure tasks were resumed; algorithm
outcomes were never replaced. This is a runtime robustness limitation, not an
algorithm failure count.

## KI-F06: Direct offline pytest can inherit an incompatible ROS plugin

Some host shells export ROS paths that expose an older `launch_testing` pytest
hook to the newer offline pytest/pluggy stack, causing collection to fail before
project tests run. Use `make test`, the offline activation helper, or the
sanitized environment command in `COMMANDS.md`. This does not affect the 706
project tests that passed in the clean release environment.

## KI-F07: The real screenshot and matched telemetry prove different things

`outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png` is a real Arena
Gazebo GUI capture with pixel and runtime provenance. It is a historical
moderate-v5 validation environment capture (benchmark provenance, not another
current release) demonstrating Jackal, Nav2 DWB, LiDAR, and dynamic actors; it
is not a camera frame from the held-out statistical episode set.

The Base--PGRR trajectory and recovery timeline in
`outputs/moderate/final/media/` come from a real identical-condition held-out
pair and bind to raw/result hashes, but they are telemetry reconstructions, not
camera screenshots. Neither evidence type may be relabeled as the other.

## KI-F08: One similarly named calibration file is not authoritative

The accepted calibration report is
`outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json`, SHA-256
`0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f`.
An untracked `outputs/moderate/final/calibration_report.json` can be produced by
applying validation calibration logic to a test table; it is empty and
rejected. It is excluded from the release manifest and must not be cited.

## KI-F09: Internal dataset suffixes cannot be renamed post hoc

Paths and records containing `moderate_v6` are bound into scenario IDs, split
hashes, row-level provenance, the final configuration, and the artifact
manifest. Changing them would invalidate the published evidence. The suffix is
an internal benchmark identity; the supported project presented to users is
the single PGRR final release.

## KI-F10: Test-set tuning remains forbidden

The final 120-condition test has been opened and is permanently frozen.
Algorithm, checkpoint, threshold, scenario, or metric changes motivated by its
outcomes require a newly named, newly seeded future study. Failed episodes may
not be filtered or replaced, and validation rows may not populate final tables.

## Historical boundary

An earlier frozen 64/64 audit is retained to prevent selective reporting:
PGRR/Base collisions were 0/24 versus 19/24, timeouts were 16/24 versus 0/24,
and goal reaches were 8/24 versus 5/24; adjusted goal-reaching was not
significant. It is never pooled with the final 600-episode result.

## KI-S01: Student smoke manifests predate the currently executed JSON files

Some early eight-family student smoke manifests record hashes that no longer
match the current generated scenario JSON files. The files themselves have
since been executed and actor motion has been audited, but the older manifests
must not be used as their current provenance authority. The train-only pilot at
`configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml` pins the current
eight hashes, and `scripts/student/validate_eight_family_pilot.py` checks them.
The old manifests remain untouched as historical development records.

## KI-S02: Extension collision labels need obstacle-type attribution

The family-2 minimal-pilot Base outcome is `COLLISION`, but its detail records
intersection with known static scenario geometry. It must not be described as
a confirmed pedestrian collision. Future extension result tables need explicit
static-obstacle versus dynamic-actor attribution before making a social-safety
claim. PGRR avoided that collision in the paired run but timed out, so the
single pair shows a safety/completion tradeoff rather than task success.

## KI-S03: Arena topic readiness can fail before an algorithm episode starts

The family-3 and family-5 Base first attempts timed out while waiting for
required ROS topics. In family 5, the runtime log also shows a Nav2 lifecycle
`change_state` response timeout. Both attempts were recorded as
`SIMULATOR_FAILURE` with zero samples and preserved. After cleanup, explicit
`_retry01` attempts produced algorithm outcomes. These infrastructure attempts
must remain outside method outcome counts, and retries must keep distinct IDs;
the pilot collector enforces that lineage.

## KI-S04: Collision avoidance does not yet become task completion in the extension pilot

The eight train-only PGRR pilot episodes contain no collision outcomes, but
seven end in `TIMEOUT` and one in `PLANNER_FAILURE`; none reaches the goal. A
hash-verified raw-trace diagnostic finds 30 recovery cycles, of which only five
end closer to the original task goal and 25 have nonpositive progress. Recovery
states occupy 39.2% of aggregate elapsed time. This is evidence of repeated,
low-yield recovery, not proof that the selected checkpoint is generally worse
or that DAgger round two overfit. Comparator expansion and any algorithm change
remain separate train/validation work and must not alter the frozen release.
At cycle level, 22/25 cycles containing learned-policy decisions have
nonpositive original-goal progress, and 54/60 learned action events are WAIT or
BACKUP. These small development counts reveal an action-diversity and progress
problem but do not isolate the learned policy from masks and emergency guards.
With an offline probe matching existing scales, all 30 cycle endings retain the
original task goal and 28 satisfy the clearance check, while none reaches
0.25 m of original-goal progress. Fourteen retrigger within 2 s, and seven lack
a complete post-cycle observation window. Missing retriggers in those seven
must not be reported as stable recovery.
The logged final action mask is parseable for 58/60 learned events, and 50 of
those expose only WAIT/BACKUP. This does not prove the mask causes timeout, but
it means model-only retraining cannot provide diverse actions in most observed
states unless the safe candidate set itself changes.
The student-extension mask-chain reconstruction finds that 46/50 final
WAIT/BACKUP-only learned events are already restricted before the first logged
mask step; three collapse at `bc_closing_side` and one at `bc_yield_mask`.
“Upstream” is only a telemetry boundary and does not yet identify a causal
function. A static call map and synthetic replay are required before proposing
any train/validation ablation.
The static runtime audit further narrows pre-yield temporary-subgoal removal to
map/connectivity, observable-scan, and path-corridor filters. Current runtime
telemetry does not record these three masks separately. Six other constraints
between closing-side and recurrent-escape telemetry are also bracketed rather
than individually logged, so observational attribution must not be presented
as a causal ablation.
The synthetic upstream replay can isolate map, scan, and corridor behavior, but
the eight real train-only logs may not contain the full map and task-path
snapshots required for exact retrospective replay. Field availability must be
audited before claiming that an existing episode can be reconstructed through
all three layers.
Exact retrospective upstream-mask replay is impossible for the eight existing
train-only logs. Although all 60 learned decisions contain pose, resampled
LiDAR, and global path, none contains an occupancy-map snapshot, original scan
angles/resolution, latched task-corridor path, or runtime mask-parameter
snapshot. Any forthcoming scan/corridor reconstruction must be labeled
approximate and must report its assumptions.
Approximate replay matches only 29/58 logged subgoal sets and falsely removes a
logged-valid action in five events. It reproduces 27/46 logged empty sets, but
the omitted map layer and asynchronous/resampled logger inputs prevent causal
credit to the scan or corridor rule. These counts are diagnostic fidelity
measurements, not navigation-performance results.
The new `MaskTraceRecorder` is a tested interface prototype, not active runtime
telemetry. Existing episodes cannot be retroactively upgraded with exact
per-layer masks, and no paper claim may imply that the frozen runs contained
this instrumentation.
Trace-on/off equality is currently established only for the pure-Python
three-layer fixtures. It does not cover ROS message timing, reason-string size,
or every downstream recovery constraint. The recorder must not be described as
integrated until those checks pass.
The recorder and its opt-in Arena launch switch are now source-integrated behind
default-off values, but it has not been exercised in a live Arena episode. The
222-test offline pass
does not establish message-timing equivalence or prove that the longer enabled
reason string is fully captured by the train-only logger. Do not enable it in a
frozen evaluation or claim retrospective layer attribution.
The WSL runtime currently reports that `docker` is unavailable and recommends
activating Docker Desktop WSL integration. The WSL project mirror also lacks
the new trace integration and selected lead-stop scenario. The checked-in
preflight is ready, but no live trace smoke can be claimed until both runtime
conditions are restored and verified.

Resolved on 2026-09-12: Docker Desktop became available in Ubuntu-22.04, the
selected files were synchronized, and the ROS overlay built. Two setup defects
were exposed and fixed without deleting their episode outcomes: an unsafe WSL
line-ending command truncated `MaskTraceRecorder`, and the launcher passed `1`
to a declared ROS bool parameter. The valid retry02 ended TIMEOUT. Its two
remaining tracebacks are known Arena shutdown cleanup (`ExternalShutdownException`
and repeated `rclpy.shutdown`), not a recovery-manager crash.

The focused mask-trace regression is clean (29 passed), but a full 780-item
Windows unit run cannot currently serve as a clean gate: its first failure is
an unrelated artifact-manifest video fixture because `ffmpeg` is absent from
the `ramp-offline` host PATH. No dependency was installed for this diagnostic,
and no full-suite pass is claimed.

The selected lead-stop validation candidate intentionally mirrors the train
prototype geometry and differs by the catalog validation seed. This is suitable
for a first cross-seed selector-path development smoke, but not sufficient as a
held-out geometry/generalization result. Static preflight also cannot guarantee
that the live interaction reaches selector recovery.

The first mask-trace summary called both validation episodes `not_triggered`
because it was validating selector traces. Raw-state audit shows that head-on
validation is actually emergency-stop-only (state 4), whereas diagonal
validation stays NORMAL with zero recorded failure score. This terminology is
now corrected in the student audit, but validation selector-layer replication
remains unresolved.

The canonical DAgger distribution comparison is not currently reproducible from
the available Windows HDF5 copies. The selected manifest expects
`dagger_coverage_safety_aligned_train.h5` with SHA-256 `d529...1948`, but only
`dagger_coverage_train.h5` with a different hash is present. The available
`multiscenario_safety_aligned_validation.h5` also differs from the manifest's
`5d44...31c92`. The later iteration-5 train file does match its manifest.

A complete local/Git-history SHA-256 scan confirms the missing selected
iteration-3 and shared-validation hashes are not recoverable from this checkout's
history. Resolving them requires a trusted external artifact source. Do not edit
the manifests or substitute the mismatched local copies.

Resolved in part on 2026-09-12: the preflighted lead-stop validation smoke
yielded 191 complete selector traces, so selector-layer telemetry now has one
cross-split replication path. Its outcome was TIMEOUT, the geometry deliberately
mirrors the train prototype, and only one validation seed was run. Navigation
success and geometry-level generalization therefore remain unresolved.

The lead-stop validation timeout diagnosis is descriptive rather than causal.
All four recovery cycles lose original-goal progress and no temporary subgoal is
selected, but the trace does not isolate directional yield, policy preference,
Nav2 execution, actor timing, or mask geometry. Changing any threshold from this
single episode would be post-hoc tuning; a controlled non-frozen comparison is
required first.

The observation shadow comparator has only offline coverage. It is not connected
to ROS callbacks, and therefore has no evidence yet for concurrent state reads,
callback timing, logging overhead, or equality on real Arena messages. Runtime
wiring must remain default off and be tested only on a fresh non-frozen episode.

The new bounded accumulator addresses memory growth but not log timing or thread
safety inside the ROS executor. Those properties remain untested until a minimal
default-off integration is characterized in a non-frozen development run.

Resolved before runtime wiring: the builder previously risked freezing a shared
float32 `base_action` input because the immutable observation container marks
arrays read-only. The builder now copies the action buffer and regression tests
cover source writability and non-aliasing. Other callback/thread-safety concerns
remain open.

The default-off observation shadow is now present in the ROS node, but the
standard wrapper does not yet forward an enable switch and no live episode has
run it. Real callback consistency, thread safety, and overhead remain unverified;
the next gate is launcher plumbing plus a fresh non-frozen preflight, not a
formal evaluation.

Launcher forwarding is now resolved and a non-frozen train smoke has passed the
static preflight. Runtime equality, callback timing, thread safety, and overhead
are still unknown until the exact files are synchronized into the WSL/Arena
runtime, the overlay is rebuilt, and one fresh diagnostic episode is executed.

The teardown summary depends on a graceful enough shutdown for the ROS node to
run `destroy_node()`. An abrupt container or process kill may leave a valid
episode outcome but no shadow summary; the validator intentionally rejects that
case rather than inferring equality from incomplete evidence.

The source manifest currently passes only against the Windows authoritative
checkout. The WSL `~/PGRR-online` checkout and container overlay may still be
stale. A 5/5 WSL hash result and a subsequent overlay build are required before
the live smoke can support a runtime-equivalence statement.

Resolved for the current checkout: WSL sources now match 5/5 and pass syntax
checks. The first ad-hoc CRLF conversion attempt was unsafe because quoting
removed trailing `r` characters; the hash gate caught it before build, and the
files were restored by the tested allowlisted synchronizer. The remaining
runtime risk is a stale ROS overlay until `make build` succeeds.

Active environment blocker: Docker Desktop is not integrated with the
`Ubuntu-22.04` WSL distro, so `docker` is absent and the Arena container build
gate exits before compilation. Starting Docker Desktop or changing its WSL
integration could not be completed unattended because Windows app approval
timed out. User action is required before the live shadow smoke can resume.

Resolved offline: an explicitly enabled candidate-builder exception previously
could escape the observation shadow and interrupt the ROS node. The comparator
now contains ordinary candidate exceptions and records them as failed evidence.
Real executor timing and teardown behavior remain unverified until Docker WSL
integration is restored and the non-frozen smoke can run.

Resolved offline: accumulator counter updates and snapshots are now protected
against concurrent callers, and returned dictionaries cannot mutate internal
evidence. This does not yet measure lock overhead or prove executor-level timing
in Arena; those remain part of the blocked non-frozen runtime smoke.

The eight-family algorithm-scenario-metric matrix is a design and train-only
development artifact, not held-out comparative evidence. There is currently no
complete four-method pilot for the new families, and several proposed mechanism
diagnostics (for example minimum clearance and independently controlled event
timing) require a telemetry/schema audit before being treated as available.
Do not infer PGRR superiority from the current eight single-pair outcomes.

Two eight-family diagnostics remain semantically unresolved even though their
input telemetry exists. `minimum_clearance_m` is ambiguous between obstacle and
human clearance, and `deadlock_duration_s` lacks a frozen speed/progress/hazard
contract. They must not appear as finalized paper metrics until the definitions
are preregistered without consulting held-out results.

The two anchor pilots show a strong final-mask association: 13/15 learned
decisions had only WAIT/BACKUP available, while 6/6 recovery cycles cleared the
diagnostic hazard and 0/6 made meaningful progress. The historical anchor logs
do not contain exact traces for every upstream mask layer, so the responsible
filter is still unknown. Do not interpret this association as proof that one
specific mask stage caused the timeouts.

Updated by exact runtime evidence: two fresh train-only anchor runs now identify
`observable_scan` as the first all-temporary-empty layer in 123/162 complete
decisions. The two outcomes are still TIMEOUT, and no validation anchor was run,
so cross-split replication and the effect of changing this layer remain unknown.
Candidate removal may be correct for collision safety; do not relax it solely to
increase subgoal availability.

The two-anchor geometry audit finds that the logged scan layer retains no 1.4 m
candidate and no 0/+30/+60 degree candidate in 162 decisions. All collision-latched
decisions are empty, but 54 non-latched decisions are empty too. The saved 180-beam
scan is not the original runtime scan: approximate replay reaches 84.16% per-action
agreement but only 45.06% whole-decision agreement. Exact attribution between the
directional endpoint and swept-capsule predicates therefore remains unresolved.

Resolved by fresh original-scan telemetry: predicate attribution is exact for the
two train anchors, and the swept-capsule predicate is the direct shared source of
all 122 empty scan outputs. Still unresolved: the binary trace does not locate the
closest point along the segment or separate initial-overlap, intermediate, and
endpoint failures. It therefore does not authorize reducing the 0.90 m margin.

Resolved by failure-location telemetry: initial-overlap handling is not the source
of the latest anchor removals. Still unresolved: the policy receives no temporary
subgoal in any of the 89 latest decisions. Fifty-five are emptied by swept-capsule
geometry and 34 by the later directional-yield constraint. A single clearance
change cannot be assumed to fix both, and either anchor may also contain a scenario
feasibility or event-semantics defect.

Resolved at the logged-mask level: the 34 scan-surviving decisions all retain only
action 2, which directional yield then removes. Still unresolved is the correct
general remedy: a non-forward candidate-shape extension, a constraint-composition
change, or both. The current anchors cannot select among these because their event
semantics are incomplete: one is persistent blockage and the other is cyclic,
unsynchronized crossing. New train/validation event-controlled variants are needed.

The eight-family extension set is not yet a paper comparison set. Although all eight
current Base runs fail and seven PGRR runs trigger recovery, PGRR reaches the goal in
0/8 single train-only pairs. Six families also declare event-control limitations.
Running more repeats now would measure unstable prototypes rather than resolve their
activation, feasibility, and recovery defects.

The event-controlled anchor contract is validated but not executable. The current
scenario actor controller has no contract-backed pre/active/released event state
machine for robot-distance or goal-distance triggers. Runtime implementation must
first prove deterministic transitions, reset behavior, logging, and isolation from
policy observations; until then the replacement anchor scenarios must not be run or
described as completed.

Partially resolved offline: the three-phase event state machine now exists and is
unit-tested, but configuration adaptation, deterministic trace evidence, ROS actor
commands, transition telemetry, and reset integration are still absent. The module's
existence alone does not make either replacement scenario executable.

Further resolved offline: configuration adaptation and four deterministic traces now
pass, including source-level policy-path isolation. Still unresolved are default-off
ROS wiring, actor command semantics, transition telemetry in episode artifacts, reset
integration, and physical post-release route feasibility. Offline traces must not be
reported as simulator episodes.

The ROS wiring preflight is resolved and reproducible, but its result deliberately
reports 0/6 runtime connections. Default-off actor-controller integration, reset
integration, event-transition publication, episode logging, launcher forwarding, and
scenario materialization remain unimplemented. Therefore no event-controlled Arena
episode exists yet, and physical trigger/release or post-release reachability is still
unproven.

Source-level default-off wiring is now present, including reset and bounded transition
logging. Still unresolved: no generated scenario contains the executable
`ramp_event_control` mapping, the modified ROS package has not been synchronized or
built in the Arena environment, and no actor trigger/release has been observed in
Gazebo. Windows-side launch scripts retain CRLF line endings; normalized-LF syntax
passes, but runtime synchronization must preserve executable LF content.

One train-only bounded lead-stop JSON now contains executable event control and a
statically feasible noncyclic exit. Its Gazebo semantics remain unverified: actor
route-clock holding, one-shot release, transition telemetry, and post-release Nav2
reachability have not yet been observed after rebuilding the WSL overlay. The
candidate must not be counted among the eight paper cases until the fixed-seed paired
runtime gate and later validation replication pass.

The bounded lead-stop event is now proven to activate and release in a real Base
episode, but activation occurs at 80 s of a 90 s episode and Base stops 0.931 m from
the goal. PGRR runtime health is unresolved independently of scene performance: one
attempt hit a pre-event SIMULATOR_FAILURE and the single retry never passed required
topic readiness. Do not tune this scene or rerun it again until a previously stable,
non-frozen PGRR control scenario distinguishes a global runtime fault from a
candidate-specific fault.

The PGRR runtime-health ambiguity is resolved by a valid 893-sample train control.
Lead-stop v2 is nevertheless unsuitable as a core case: its Base failure is a static
geometry collision, while PGRR ends in recovery_sequence_timeout rather than reaching
the goal. Further edits to this narrow-shelf variant risk optimizing around a mixed
static/dynamic mechanism. Prefer an open-geometry closing-gap candidate next.

The first open-geometry closing-gap revision removes the static-wall confound and its
event sequence works, but it does not create comparative separation: Base and PGRR
both time out about 2.1 m from the goal after all four event transitions. Treat this as
a valid negative result, not a paper case. Repeated seed search or threshold tuning on
this candidate would violate the screening discipline; move to a distinct mechanism.

Only five of the eight frozen final families contain any matched condition where Base
fails to reach and PGRR reaches. Group blocking, opposite streams, and overtaking have
15/15 Base and PGRR goal reaches each, so an honest eight-case illustration can span
five mechanisms but cannot be described as eight independently demonstrated mechanism
families. New mechanisms require separate train/validation development evidence.

The supervisor requirement is now confirmed to be eight scenarios rather than eight
selected episode examples. No newly developed scenario currently satisfies the full
positive promotion requirement: the eight extension prototypes have 0/8 PGRR goals,
and the later event-controlled candidates are negative or incomplete. The frozen
eight-row shortlist must not be counted toward this target. A scenario-level replicated
promotion rule is still required before screening resumes.

The generated scenario JSON and raw JSONL/metadata/outcome sidecars for the eight
post-hoc qualitative cases are not present in the current Windows or WSL checkout.
Their paths and hashes remain bound in the frozen result, so tabular evidence is usable,
but seven additional trajectory plots cannot be regenerated locally. Do not rerun the
frozen test or invent paths; recover the immutable archive if more plots are required.

The first new medium crossing-flow anchor is ready for one fixed-seed runtime pair,
but the current host exposes neither a working Docker client/server nor a launchable
Docker Desktop installation/process. The protected runner exits before any episode,
so there is no partial Base/PGRR result to interpret. Do not change the scenario seed,
checkpoint, thresholds, or JSON to work around this environment blocker; restore the
existing Arena Docker runtime and rerun the exact pinned pair.

The Docker blocker above is resolved and the exact pair has run. The candidate itself
does not satisfy the positive scenario contract: PGRR avoided Base's pedestrian
collision but timed out 3.917 m from the goal after restoring the original goal. This
is now a closed negative screen, not an environment ambiguity. Do not retry another
seed, extend the timeout, or tune recovery thresholds for this candidate.

The v1 horizon confound is resolved in v2 by a general 15 m route constraint while
preserving the interaction. The positive Base-collision/PGRR-goal result currently has
only one seed, so reproducibility is still unknown. Do not describe it as one of eight
completed paper scenarios until the frozen v2 definition passes predeclared train and
independent validation repeat gates.

Crossing-flow v2 now passes its train replication gate with 3/3 positive pairs, but no
independent validation has been materialized or run. One r02 PGRR startup produced a
zero-sample INVALID_RESET before the sole same-seed retry succeeded; both attempts are
retained. The remaining issue is external validity, not train reproducibility. Until a
predeclared independent validation gate passes, report one train-replicated candidate
and zero fully validated new scenarios.

Crossing-flow v2's external-validation issue is resolved: all three independent seeds
produce Base collision/PGRR goal reach with no retries. The broader eight-scenario
requirement is not resolved; only 1/8 mechanisms has passed the full train-plus-
validation funnel. Three validation pairs in one mechanism do not establish general
superiority or statistical significance. Further work must screen distinct interaction
mechanisms without revisiting or expanding this now-closed design.

The independent-confirmation issue for goal-approach lateral v2 is resolved with 3/3
qualifying validation pairs, so it is now scenario 2/8. The remaining breadth gap is
6 scenarios. Within the user's four-priority program, bounded closing-gap and bounded
lead-stop still require optimization and the same train/validation funnel.

Bounded closing-gap v3 is positive at one train seed but reached at sample 892 of a
900-sample horizon, leaving little timing margin. This is not yet a confirmed third
scenario. Its immediate uncertainty is reproducibility under predeclared train seeds;
do not extend timeout, select favorable seeds, or change recovery settings.

The bounded closing-gap v3 reproducibility uncertainty is now resolved negatively.
Only r00 reached the goal; r01 and r02 timed out with about 2.41 m and 2.01 m remaining.
Both traces released both actors and restored the original goal, but each executed two
recovery cycles with nonpositive cycle-level goal progress and returned to sustained
normal navigation only around 69 s. This candidate is closed at 1/3 and must not be
rescued by favorable-seed selection, a longer timeout, or post-hoc threshold changes.
