# Commands

This is the command sheet for the single supported PGRR final release. It
contains current build, validation, reproduction, and branch-publication
commands only. Intermediate experiment commands remain recoverable from Git
history and run manifests.

## 1. Enter the repository

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
git status --short --branch
```

Do not mix the host ROS environment with Conda. The online runtime must use the
pinned Humble container/overlay; offline commands must use `ramp-offline` with
foreign ROS variables removed.

## 2. Bootstrap and verify

```bash
make preflight
make conda
make arena
make build
make test
```

If a direct offline Python command is needed from a shell that advertises ROS,
use the sanitized form:

```bash
env \
  -u PYTHONPATH \
  -u AMENT_PREFIX_PATH \
  -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH \
  -u ROS_DISTRO \
  -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  conda run --no-capture-output -n ramp-offline \
  python -m pytest -q
```

This prevents the ROS `launch_testing` pytest plugin from contaminating the
offline pytest environment.

## 3. Bounded smoke and small reproduction

```bash
make smoke SEED=0 HEADLESS=1
make reproduce-small SEED=0
```

The smoke command checks startup, `/clock`, TF, LiDAR, odometry, robot spawn,
and goal acceptance. It is not an algorithm-result episode. The small
reproduction checks data/model/statistics contracts and does not launch the
600-episode evaluation.

## 4. Inspect the published result without rerunning simulation

```bash
env \
  -u PYTHONPATH \
  -u AMENT_PREFIX_PATH \
  -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH \
  -u ROS_DISTRO \
  -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  conda run --no-capture-output -n ramp-offline \
  python - <<'PY'
from pathlib import Path
import json
import pandas as pd

root = Path("outputs/moderate/final")
results = pd.read_parquet(root / "results.parquet")
run = json.loads((root / "run_manifest.json").read_text())

print("run_id:", run["run_id"])
print("rows:", len(results))
print(results.groupby(["source_policy", "outcome"]).size().unstack(fill_value=0))
PY
```

Expected logical result: 600 rows, 120 per method, with run ID
`95ec74c511bb`.

## 5. Rebuild the final paper/report/PPT from published evidence

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
```

This command does not start Arena and does not read `data/raw`. It validates
the published inputs, regenerates result-dependent assets, builds the exact
8-page paper, exact 32-page report, and 30-slide PPTX/PDF, and writes a
candidate artifact manifest.

Maintainers who possess the private raw JSONL streams may explicitly recollect
the final bundle before rebuilding:

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=1 \
scripts/reproduce_paper.sh
```

`PGRR_RECOLLECT_RAW=1` recollects and verifies existing raw episodes; it does
not run simulation. Never point it at validation, pilot, smoke, or historical
results.

## 6. Validate the committed release from a clean checkout

```bash
test -z "$(git status --porcelain --untracked-files=all)"
PGRR_RELEASE_MODE=1 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
test -z "$(git status --porcelain --untracked-files=all)"
```

Release mode is validate-only. It reconstructs scientific provenance, compares
the 96 declared artifact hashes and document page counts, runs the privacy
audit, and must leave the checkout unchanged.

## 7. Full held-out evaluation — intentional rerun only

The published run is complete. Do not invoke this section merely to rebuild
documents. A scientifically independent rerun requires a clean checkout of the
frozen evaluation commit, the pinned Arena runtime, the accepted calibration
report, adequate disk space, and no other Arena containers.

```bash
git worktree add ../PGRR-evaluation-reproduction \
  6916e7cd586acfbe200045e49b093039e2a6980e
cd ../PGRR-evaluation-reproduction
make verify-calibration
test ! -e outputs/moderate/independent_reproduction
make evaluate-final \
  MODERATE_ANALYSIS_DIR=outputs/moderate/independent_reproduction
```

The target uses the frozen five methods, 120 shared conditions per method,
240 s horizon, and six workers. Resume only incomplete tasks with the same
configuration and concurrency. Never rerun `GOAL_REACHED`, `COLLISION`,
`TIMEOUT`, or `PLANNER_FAILURE`; only explicitly classified
`SIMULATOR_FAILURE` and `INVALID_RESET` attempts are retryable.

## 8. Authoritative release checks

```bash
make test
make privacy-check
python scripts/paper/validate_final_pdf_text.py paper/main.pdf
pdfinfo paper/main.pdf | grep '^Pages:'
pdfinfo report/PGRR_technical_report_zh.pdf | grep '^Pages:'
pdfinfo presentation/PGRR_report_zh.pdf | grep '^Pages:'
```

The expected counts are 8, 32, and 30. The release validator in section 6
remains the final authority because it also checks every artifact SHA,
canonical media hash, report/PPT data structure, and privacy state. Font
embedding is checked during the development document build whose accepted PDFs
are then hash-bound by release mode.

## 9. Publish the synchronized branches

After tests and clean-checkout release validation pass:

```bash
git push origin HEAD:home
git fetch origin home
git switch main
git merge --no-ff origin/home
PGRR_RELEASE_MODE=1 PGRR_RECOLLECT_RAW=0 scripts/reproduce_paper.sh
git push origin main
```

If `main` is already checked out in another worktree, run the final four lines
there instead of switching in the current worktree. The merge must contain the
exact release commit already pushed to `home`. Do not force-push either branch.

## 10. Validate the train-only eight-family student pilot

```bash
conda run -n ramp-offline python scripts/student/validate_eight_family_pilot.py \
  --output outputs/student/eight_family_pilot/validation_report.json
conda run -n ramp-offline python -m pytest \
  tests/unit/test_validate_eight_family_pilot.py \
  tests/unit/test_analyze_recovery_trace.py \
  tests/unit/test_analyze_privileged_actor_motion.py -q
```

Compile, run, and audit goal-approach v2 independent validation:

```powershell
$env:PYTHONPATH=(Resolve-Path packages/ramp_core).Path
0..2 | ForEach-Object {
  $id = 'r0' + $_
  & .\.conda\ramp-offline\python.exe scripts/student/compile_goal_approach_lateral_v2.py `
    --config "configs/experiments/pgrr_goal_approach_lateral_v2_validation_$id.yaml" `
    --output-root "outputs/student/goal_approach_lateral_v2_validation_$id"
}
wsl -d Ubuntu-22.04 -- bash -lc "DRY_RUN=0 bash '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_goal_approach_lateral_v2_validation.sh'"
& .\.conda\ramp-offline\python.exe scripts/student/summarize_goal_approach_lateral_v2_validation.py `
  --runtime outputs/student/goal_approach_lateral_v2_validation/runtime `
  --json-output outputs/student/goal_approach_lateral_v2_validation/validation_summary.json `
  --markdown-output outputs/student/goal_approach_lateral_v2_validation/validation_summary.md
```

This validates inputs and provenance only. It does not start ROS, train a
model, run the 32 pilot attempts, or materialize a test split.

Generate and dry-run the 16-attempt minimal Base/PGRR plan from Windows:

```powershell
conda run -n ramp-offline python scripts/student/prepare_eight_family_minimal_pilot.py
wsl -d Ubuntu-22.04 -- bash "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_eight_family_minimal_pilot.sh"
```

Run exactly one pair by setting `DRY_RUN=0`, an even `START_AT`, and `LIMIT=2`.
For example, family 3 uses `START_AT=4`. Existing raw/log outputs are never
overwritten. Do not automatically retry algorithm outcomes.

After an explicitly recorded `SIMULATOR_FAILURE` or `INVALID_RESET`, retry one
method with a new attempt ID, for example:

```powershell
wsl -d Ubuntu-22.04 -- env DRY_RUN=0 METHODS=base START_AT=4 LIMIT=1 RETRY_SUFFIX=_retry01 bash "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_eight_family_minimal_pilot.sh"
```

The collector preserves the original infrastructure attempt and selects the
first non-infrastructure retry for the paired method result.

After all eight pairs are collected, render the train-only diagnostic table:

```powershell
conda run -n ramp-offline python scripts/student/render_eight_family_minimal_pilot_summary.py
```

The generated CSV and Markdown are development summaries. They are not inputs
to the frozen release paper or final statistical tables.

Diagnose original-goal progress and recovery-state occupancy from the eight
existing PGRR JSONL logs (run from Windows with the logs in the WSL runtime):

```powershell
wsl -d Ubuntu-22.04 -- python3 "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/diagnose_eight_family_recovery_progress.py" `
  --progress "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/eight_family_pilot/minimal_pair_progress.json" `
  --data-root /home/preface/PGRR-online/data/raw `
  --json-output "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/eight_family_pilot/recovery_progress_diagnostic.json" `
  --csv-output "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/eight_family_pilot/recovery_progress_diagnostic.csv" `
  --cycle-csv-output "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/eight_family_pilot/recovery_cycle_classification.csv" `
  --markdown-output "/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/eight_family_pilot/recovery_progress_diagnostic.md"
```

The script verifies each raw-log hash before calculating distance to the first
logged task goal, recovery-cycle progress, state occupancy, and low-speed
fractions. It is a development diagnostic and does not mutate or read the
frozen final benchmark.

Run the recovery-cycle interface and existing core regression tests directly
from the offline Python environment:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python -m pytest -q `
  tests/unit/test_recovery_cycle_progress.py `
  tests/unit/test_recovery_options.py `
  tests/unit/test_state_machine.py
```

The prototype is not imported by the ROS recovery manager; this command is an
offline contract check, not an Arena evaluation.

Apply the observable contract to existing WSL JSONL logs without installing
anything in WSL or changing the runtime:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/adapt_recovery_cycles_to_progress_contract.py `
  --progress outputs/student/eight_family_pilot/minimal_pair_progress.json `
  --data-root '\\wsl.localhost\Ubuntu-22.04\home\preface\PGRR-online\data\raw' `
  --minimum-progress-m 0.25 `
  --minimum-clear-frames 4 `
  --rapid-retrigger-window-s 2.0 `
  --clear-failure-score-threshold 0.35 `
  --original-goal-tolerance-m 0.001 `
  --json-output outputs/student/eight_family_pilot/recovery_contract_probe.json `
  --csv-output outputs/student/eight_family_pilot/recovery_contract_probe.csv
```

The numeric arguments are an explicitly labeled existing-contract probe. They
do not update the selected checkpoint, ROS parameters, or frozen test evidence.

Reproduce the read-only mask/policy/emergency attribution:

```powershell
python scripts/student/analyze_recovery_control_attribution.py `
  --progress outputs/student/eight_family_pilot/minimal_pair_progress.json `
  --data-root '\\wsl.localhost\Ubuntu-22.04\home\preface\PGRR-online\data\raw' `
  --json-output outputs/student/eight_family_pilot/recovery_control_attribution.json `
  --csv-output outputs/student/eight_family_pilot/recovery_control_attribution.csv
```

This command parses existing telemetry only. It neither reruns Arena nor changes
the action masks used by the frozen release.

Reconstruct the ordered, logged pre/post mask chain from the train-only traces:

```powershell
python scripts/student/analyze_mask_constraint_chain.py `
  --progress outputs/student/eight_family_pilot/minimal_pair_progress.json `
  --data-root '\\wsl.localhost\Ubuntu-22.04\home\preface\PGRR-online\data\raw' `
  --json-output outputs/student/eight_family_pilot/mask_constraint_chain.json `
  --csv-output outputs/student/eight_family_pilot/mask_constraint_chain.csv
```

This is a hash-verified reconstruction of recorded transitions, not a rerun or
counterfactual mask ablation. `UPSTREAM_BEFORE_FIRST_LOGGED_STEP` identifies a
telemetry boundary only; it does not name a causal function.

Audit the static runtime mask-call order without importing ROS:

```powershell
python scripts/student/audit_runtime_mask_pipeline.py `
  --source ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py `
  --json-output outputs/student/eight_family_pilot/runtime_mask_pipeline_audit.json `
  --markdown-output outputs/student/eight_family_pilot/runtime_mask_pipeline_audit.md
```

This command parses Python source with `ast`; it does not start ROS, load a
checkpoint, or execute an algorithm episode.

## Scientific boundary

The earlier 64/64 audit remains part of the record: PGRR/Base collisions were
0/24 versus 19/24, timeouts 16/24 versus 0/24, and goal reaches 8/24 versus
5/24; the adjusted goal-reaching comparison was not significant. Those rows
are not inputs to any command that builds the final 600-episode result.
Run the deterministic three-layer synthetic mask replay:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/replay_upstream_mask_layers.py `
  --json-output outputs/student/eight_family_pilot/upstream_mask_layer_replay.json `
  --csv-output outputs/student/eight_family_pilot/upstream_mask_layer_replay.csv
```

The fixtures exercise the production core helpers offline; they do not replay
a real episode or change a runtime configuration.
Audit field sufficiency for replaying masks from existing WSL logs:

```powershell
python scripts/student/audit_raw_mask_replay_fields.py `
  --progress outputs/student/eight_family_pilot/minimal_pair_progress.json `
  --data-root '\\wsl.localhost\Ubuntu-22.04\home\preface\PGRR-online\data\raw' `
  --json-output outputs/student/eight_family_pilot/raw_mask_replay_field_audit.json
```

The command reads and hash-checks existing train-only logs and does not execute
Arena.
Approximately replay the recorded scan and path-corridor layers:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/replay_real_scan_corridor_masks.py `
  --progress outputs/student/eight_family_pilot/minimal_pair_progress.json `
  --data-root '\\wsl.localhost\Ubuntu-22.04\home\preface\PGRR-online\data\raw' `
  --json-output outputs/student/eight_family_pilot/approximate_real_mask_replay.json `
  --csv-output outputs/student/eight_family_pilot/approximate_real_mask_replay.csv
```

The replay assumes the checked-in 270-degree/180-bin scan geometry and mask
parameters, omits the unavailable map layer, and must remain labeled
approximate.
Validate the unintegrated train-only mask telemetry contract:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python -m pytest -q tests/unit/test_mask_trace.py
```

This test imports only `ramp_core`; it does not source ROS or start Arena.

Validate the default-off minimal ROS mask-trace integration offline:

```powershell
$env:PYTHONPATH = ((Resolve-Path packages/ramp_core).Path + ';' + `
  (Resolve-Path packages/ramp_ml).Path)
python -m pytest -q `
  tests/unit/test_mask_trace.py `
  tests/unit/test_replay_upstream_mask_layers.py `
  tests/unit/test_recovery_manager_mask_trace_integration.py `
  tests/unit/test_baseline_profiles.py
```

This check does not start ROS or Arena. A future live smoke may set
`enable_upstream_mask_trace:=true` only in a non-frozen train-only profile.

Run the prepared non-frozen PGRR mask-trace smoke from the WSL project mirror:

```bash
cd ~/PGRR-online
RAMP_SOURCE_POLICY=pgrr \
RAMP_ENABLE_UPSTREAM_MASK_TRACE=1 \
RAMP_EPISODE_ID=pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912 \
RAMP_EPISODE_TIMEOUT_S=90 \
SCENARIO=outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json \
scripts/arena/run_baseline_episode.sh
```

This uses a new train-only episode ID and only enables diagnostics. It must not
be pointed at `moderate_v6`, `outputs/moderate/final`, or another frozen split.

Regenerate the structured safety preflight before that run:

```powershell
python scripts/student/preflight_mask_trace_smoke.py `
  --scenario outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json `
  --episode-id pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912 `
  --output outputs/student/eight_family_pilot/mask_trace_smoke_preflight.json
```

Validate a completed live mask-trace smoke without making a performance claim:

```bash
cd ~/PGRR-online
python3 scripts/student/validate_mask_trace_smoke.py \
  --jsonl data/raw/pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912_retry02.jsonl \
  --outcome data/raw/pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912_retry02.outcome.json \
  --runtime-log outputs/logs/baseline/pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912_retry02_runtime.log \
  --output outputs/student/eight_family_pilot/mask_trace_smoke_retry02_validation.json
```

The validator requires the three upstream stages exactly once and in order on
every traced decision, checks JSONL/outcome sample counts, and reports expected
Arena shutdown exceptions separately from known recovery-manager failures.

Aggregate completed and non-triggered trace smokes while preserving the split:

```powershell
python scripts/student/summarize_mask_trace_replication.py `
  outputs/student/eight_family_pilot/mask_trace_smoke_retry02_validation.json `
  outputs/student/eight_family_pilot/mask_trace_diagonal_train_validation.json `
  outputs/student/eight_family_pilot/mask_trace_diagonal_validation_validation.json `
  outputs/student/eight_family_pilot/mask_trace_headon_train_validation.json `
  outputs/student/eight_family_pilot/mask_trace_headon_validation_validation.json `
  --output outputs/student/eight_family_pilot/mask_trace_replication_summary.json
```

Generate exactly one non-test validation prototype instead of materializing all
preceding train conditions:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/compile_extension_train_validation.py `
  --split validation --limit 1
```

Generate and statically preflight the selected non-frozen lead-stop validation
candidate (this does not start Arena):

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/compile_lead_stop_smoke.py --split validation
python scripts/student/preflight_mask_trace_smoke.py `
  --scenario outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_validation_r00_s93500.json `
  --episode-id pgrr_masktrace_leadstop_validation_r00_20260912 `
  --allow-validation `
  --output outputs/student/eight_family_pilot/mask_trace_leadstop_validation_preflight.json
```

Regenerate the Homework 2 pre-refactor structural snapshot without importing
ROS or changing runtime code:

```powershell
python scripts/student/audit_recovery_manager_structure.py `
  --output outputs/student/refactor_baseline/recovery_manager_structure.json
```

Regenerate the development-only evidence-to-claim ledger for Homework 3 and
paper preparation:

```powershell
python scripts/student/build_extension_claim_ledger.py `
  --json-output outputs/student/paper_claim_ledger/extension_claim_ledger.json `
  --markdown-output outputs/student/paper_claim_ledger/extension_claim_ledger.md
```

Compile, run, and summarize the predeclared bounded closing-gap v3 train replication:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/compile_closing_gap_bounded_v2.py `
  --config configs/experiments/pgrr_closing_gap_bounded_v3_train_r01.yaml `
  --output-root outputs/student/closing_gap_bounded_v3_train_r01
python scripts/student/compile_closing_gap_bounded_v2.py `
  --config configs/experiments/pgrr_closing_gap_bounded_v3_train_r02.yaml `
  --output-root outputs/student/closing_gap_bounded_v3_train_r02
wsl -d Ubuntu-22.04 -- bash -lc "DRY_RUN=0 bash '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_closing_gap_bounded_v3_train_replication.sh'"
python scripts/student/summarize_closing_gap_bounded_v3_replication.py `
  --screen-runtime outputs/student/closing_gap_bounded_v3_screen/runtime `
  --replication-runtime outputs/student/closing_gap_bounded_v3_replication/runtime `
  --json-output outputs/student/closing_gap_bounded_v3_replication/replication_summary.json `
  --markdown-output outputs/student/closing_gap_bounded_v3_replication/replication_summary.md
```

Run and summarize the frozen goal-approach v2 train replication gate:

```powershell
$env:PYTHONPATH=(Resolve-Path packages/ramp_core).Path
& .\.conda\ramp-offline\python.exe scripts/student/compile_goal_approach_lateral_v2.py `
  --config configs/experiments/pgrr_goal_approach_lateral_v2_train_r01.yaml `
  --output-root outputs/student/goal_approach_lateral_v2_train_r01
& .\.conda\ramp-offline\python.exe scripts/student/compile_goal_approach_lateral_v2.py `
  --config configs/experiments/pgrr_goal_approach_lateral_v2_train_r02.yaml `
  --output-root outputs/student/goal_approach_lateral_v2_train_r02
wsl -d Ubuntu-22.04 -- bash -lc "DRY_RUN=0 bash '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_goal_approach_lateral_v2_train_replication.sh'"
& .\.conda\ramp-offline\python.exe scripts/student/summarize_goal_approach_lateral_v2_replication.py `
  --screen-runtime outputs/student/goal_approach_lateral_v2_screen/runtime `
  --replication-runtime outputs/student/goal_approach_lateral_v2_replication/runtime `
  --json-output outputs/student/goal_approach_lateral_v2_replication/replication_summary.json `
  --markdown-output outputs/student/goal_approach_lateral_v2_replication/replication_summary.md
```

Summarize the fixed crossing-flow v2 train replication evidence, including the
preserved zero-sample INVALID_RESET and sole retry:

```powershell
python scripts/student/summarize_crossing_flow_v2_replication.py `
  --screen-runtime outputs/student/advantage_scenario_screen_v2/runtime `
  --replication-runtime outputs/student/advantage_scenario_screen_v2_replication/runtime `
  --json-output outputs/student/advantage_scenario_screen_v2_replication/replication_summary.json `
  --markdown-output outputs/student/advantage_scenario_screen_v2_replication/replication_summary.md

$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
& .\.conda\ramp-offline\python.exe -m pytest `
  tests/unit/test_summarize_crossing_flow_v2_replication.py `
  tests/unit/test_compile_crossing_flow_anchor.py -q
```

Generate, dry-run, execute, and summarize the frozen crossing-flow v2 independent
validation gate:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
& .\.conda\ramp-offline\python.exe scripts/student/compile_crossing_flow_anchor.py `
  --config configs/experiments/pgrr_advantage_screen_crossing_v2_validation_r00.yaml `
  --output-root outputs/student/advantage_scenario_screen_v2_validation_r00

wsl -d Ubuntu-22.04 -- bash -lc "DRY_RUN=0 bash '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_crossing_flow_v2_validation.sh'"

& .\.conda\ramp-offline\python.exe scripts/student/summarize_crossing_flow_v2_validation.py `
  --runtime outputs/student/advantage_scenario_screen_v2_validation/runtime `
  --json-output outputs/student/advantage_scenario_screen_v2_validation/validation_summary.json `
  --markdown-output outputs/student/advantage_scenario_screen_v2_validation/validation_summary.md
```

Generate and summarize the fixed goal-approach lateral v2 single-seed screen:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
& .\.conda\ramp-offline\python.exe scripts/student/compile_goal_approach_lateral_v2.py

wsl -d Ubuntu-22.04 -- bash -lc "DRY_RUN=0 bash '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/scripts/student/run_goal_approach_lateral_v2_pair.sh'"

& .\.conda\ramp-offline\python.exe scripts/student/summarize_goal_approach_lateral_v2_screen.py `
  --runtime outputs/student/goal_approach_lateral_v2_screen/runtime `
  --output outputs/student/goal_approach_lateral_v2_screen/screen_summary.json
```

Compile and run the design-corrected 15 m crossing-flow v2 pair:

```powershell
$env:PYTHONPATH='packages/ramp_core'
& 'C:\Users\28646\miniconda3\envs\ramp-offline\python.exe' `
  scripts/student/compile_crossing_flow_anchor.py `
  --config configs/experiments/pgrr_advantage_screen_crossing_v2.yaml `
  --output-root outputs/student/advantage_scenario_screen_v2
```

```bash
cd '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'
DRY_RUN=0 bash scripts/student/run_crossing_flow_anchor_v2_pair.sh
```

Compile and offline-screen the first train-only crossing-flow advantage anchor:

```powershell
$env:PYTHONPATH='packages/ramp_core'
& 'C:\Users\28646\miniconda3\envs\ramp-offline\python.exe' `
  scripts/student/compile_crossing_flow_anchor.py
```

After the existing Docker/Arena runtime is restored, execute the one fixed-seed pair:

```bash
cd '/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'
DRY_RUN=0 bash scripts/student/run_crossing_flow_anchor_pair.sh
```

Generate and verify the first train-only bounded lead-stop event candidate:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
& .\.conda\ramp-offline\python.exe scripts/student/compile_event_controlled_lead_stop.py
& .\.conda\ramp-offline\python.exe -m ruff check `
  scripts/student/compile_event_controlled_lead_stop.py `
  tests/unit/test_compile_event_controlled_lead_stop.py
& .\.conda\ramp-offline\python.exe -m pytest -q `
  tests/unit/test_compile_event_controlled_lead_stop.py `
  tests/unit/test_scenario_event_state_machine.py `
  tests/unit/test_scenario_event_runtime.py `
  tests/unit/test_event_contract_adapter_and_probe.py
```

Run the default-off ROS event-control wiring preflight and its focused regression set:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
conda run -p .conda/ramp-offline python -m pytest -q `
  tests/unit/test_preflight_event_control_ros_wiring.py `
  tests/unit/test_scenario_event_state_machine.py `
  tests/unit/test_event_contract_adapter_and_probe.py `
  tests/unit/test_validate_event_controlled_anchor_contract.py

conda run -p .conda/ramp-offline python `
  scripts/student/preflight_event_control_ros_wiring.py `
  --root . `
  --output outputs/student/anchor_feasibility/event_control_ros_wiring_preflight.json
```

Summarize exact swept-capsule failure locations and downstream final-mask availability:

```powershell
python scripts/student/summarize_capsule_failure_locations.py `
  --jsonl data/raw/pgrr_anchor_capsuleloc_goalapproach_train_r00_20260915.jsonl `
  --jsonl data/raw/pgrr_anchor_capsuleloc_leadstop_train_r00_20260915.jsonl `
  --json-output outputs/student/anchor_feasibility/two_anchor_capsule_failure_locations.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_capsule_failure_locations.md
```

Audit exact downstream constraint intersections:

```powershell
python scripts/student/audit_anchor_constraint_intersection.py `
  --jsonl data/raw/pgrr_anchor_capsuleloc_goalapproach_train_r00_20260915.jsonl `
  --jsonl data/raw/pgrr_anchor_capsuleloc_leadstop_train_r00_20260915.jsonl `
  --json-output outputs/student/anchor_feasibility/two_anchor_constraint_intersection.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_constraint_intersection.md
```

Audit whether the two anchor JSON files implement their named events:

```powershell
python scripts/student/audit_anchor_scenario_semantics.py `
  --scenario outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json `
  --scenario outputs/student/families_7_8_smoke/generated/arena/map_empty/goal_approach_lateral_interruption_low_train_r00_s91700.json `
  --json-output outputs/student/anchor_feasibility/two_anchor_scenario_semantics.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_scenario_semantics.md
```

Triage all eight development families against core-comparison promotion gates:

```powershell
python scripts/student/triage_eight_family_core_readiness.py `
  --config configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml `
  --pair-root outputs/student/eight_family_pilot/pair_results `
  --json-output outputs/student/eight_family_pilot/core_readiness_triage.json `
  --markdown-output outputs/student/eight_family_pilot/core_readiness_triage.md
```

Validate the non-executable event-controlled anchor contract:

```powershell
python scripts/student/validate_event_controlled_anchor_contract.py `
  --config configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml `
  --output outputs/student/anchor_feasibility/event_controlled_anchor_contract_validation.json
```

Run the isolated event-state-machine unit gate from the core package directory:

```powershell
cd packages/ramp_core
python -m pytest ../../tests/unit/test_scenario_event_state_machine.py -q
python -m ruff check ramp_core/scenario ../../tests/unit/test_scenario_event_state_machine.py
```

Generate the four deterministic offline event-contract traces:

```powershell
python scripts/student/probe_event_control_contract.py `
  --config configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml `
  --output outputs/student/anchor_feasibility/event_controlled_anchor_offline_traces.json
```

Audit exact logged observable-scan removals and the bounded 180-beam approximation:

```powershell
$env:PYTHONPATH = "packages/ramp_core;packages/ramp_ml"
python scripts/student/audit_anchor_observable_scan_geometry.py `
  --jsonl data/raw/pgrr_anchor_masktrace_goalapproach_train_r00_20260915.jsonl `
  --jsonl data/raw/pgrr_anchor_masktrace_leadstop_train_r00_20260915.jsonl `
  --json-output outputs/student/anchor_feasibility/two_anchor_observable_scan_geometry_audit.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_observable_scan_geometry_audit.md
```

Summarize exact original-LaserScan predicate traces from the two fresh anchors:

```powershell
$env:PYTHONPATH = "packages/ramp_core;packages/ramp_ml"
python scripts/student/summarize_exact_scan_predicates.py `
  --jsonl data/raw/pgrr_anchor_predicates_goalapproach_train_r00_20260915.jsonl `
  --jsonl data/raw/pgrr_anchor_predicates_leadstop_train_r00_20260915.jsonl `
  --json-output outputs/student/anchor_feasibility/two_anchor_exact_scan_predicates.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_exact_scan_predicates.md
```

Generate and validate the Homework 3 eight-family algorithm-scenario-metric matrix:

```powershell
python scripts/student/build_eight_family_method_metric_matrix.py `
  --json-output outputs/student/paper_design/eight_family_method_metric_matrix.json `
  --markdown-output outputs/student/paper_design/eight_family_method_metric_matrix.md

python -m pytest tests/unit/test_build_eight_family_method_metric_matrix.py -q
python -m ruff check scripts/student/build_eight_family_method_metric_matrix.py tests/unit/test_build_eight_family_method_metric_matrix.py
python -m json.tool outputs/student/paper_design/eight_family_method_metric_matrix.json
```

Audit telemetry coverage for every metric requested by the eight-family matrix:

```powershell
python scripts/student/audit_eight_family_metric_telemetry.py `
  --matrix outputs/student/paper_design/eight_family_method_metric_matrix.json `
  --json-output outputs/student/paper_design/eight_family_metric_telemetry_coverage.json `
  --markdown-output outputs/student/paper_design/eight_family_metric_telemetry_coverage.md

python -m pytest tests/unit/test_audit_eight_family_metric_telemetry.py -q
python -m ruff check scripts/student/audit_eight_family_metric_telemetry.py tests/unit/test_audit_eight_family_metric_telemetry.py
python -m json.tool outputs/student/paper_design/eight_family_metric_telemetry_coverage.json
```

Generate the hash-bound two-anchor recovery failure diagnosis:

```powershell
python scripts/student/build_anchor_failure_diagnosis.py `
  --pairs outputs/student/eight_family_pilot/minimal_pair_summary.csv `
  --progress outputs/student/eight_family_pilot/recovery_progress_diagnostic.json `
  --attribution outputs/student/eight_family_pilot/recovery_control_attribution.json `
  --contract outputs/student/eight_family_pilot/recovery_contract_probe.json `
  --json-output outputs/student/anchor_feasibility/two_anchor_failure_diagnosis.json `
  --markdown-output outputs/student/anchor_feasibility/two_anchor_failure_diagnosis.md

python -m pytest tests/unit/test_build_anchor_failure_diagnosis.py -q
python -m ruff check scripts/student/build_anchor_failure_diagnosis.py tests/unit/test_build_anchor_failure_diagnosis.py
python -m json.tool outputs/student/anchor_feasibility/two_anchor_failure_diagnosis.json
```

Preflight and run the two non-frozen full-layer anchor traces:

```bash
RAMP_SOURCE_POLICY=pgrr RAMP_ENABLE_UPSTREAM_MASK_TRACE=1 \
RAMP_EPISODE_ID=pgrr_anchor_masktrace_goalapproach_train_r00_20260915 \
RAMP_EPISODE_TIMEOUT_S=90 \
SCENARIO=outputs/student/families_7_8_smoke/generated/arena/map_empty/goal_approach_lateral_interruption_low_train_r00_s91700.json \
scripts/arena/run_baseline_episode.sh

RAMP_SOURCE_POLICY=pgrr RAMP_ENABLE_UPSTREAM_MASK_TRACE=1 \
RAMP_EPISODE_ID=pgrr_anchor_masktrace_leadstop_train_r00_20260915 \
RAMP_EPISODE_TIMEOUT_S=90 \
SCENARIO=outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json \
scripts/arena/run_baseline_episode.sh
```

Validate and aggregate their exact layer traces:

```powershell
python scripts/student/validate_mask_trace_smoke.py `
  --jsonl data/raw/pgrr_anchor_masktrace_goalapproach_train_r00_20260915.jsonl `
  --outcome data/raw/pgrr_anchor_masktrace_goalapproach_train_r00_20260915.outcome.json `
  --runtime-log outputs/student/anchor_feasibility/runtime_logs/pgrr_anchor_masktrace_goalapproach_train_r00_20260915_runtime.log `
  --output outputs/student/anchor_feasibility/goal_approach_full_layer_mask_trace_validation.json

python scripts/student/validate_mask_trace_smoke.py `
  --jsonl data/raw/pgrr_anchor_masktrace_leadstop_train_r00_20260915.jsonl `
  --outcome data/raw/pgrr_anchor_masktrace_leadstop_train_r00_20260915.outcome.json `
  --runtime-log outputs/student/anchor_feasibility/runtime_logs/pgrr_anchor_masktrace_leadstop_train_r00_20260915_runtime.log `
  --output outputs/student/anchor_feasibility/lead_stop_full_layer_mask_trace_validation.json

python scripts/student/summarize_mask_trace_replication.py `
  outputs/student/anchor_feasibility/goal_approach_full_layer_mask_trace_validation.json `
  outputs/student/anchor_feasibility/lead_stop_full_layer_mask_trace_validation.json `
  --output outputs/student/anchor_feasibility/two_anchor_full_layer_mask_summary.json
```

Preflight the default-off observation-shadow smoke without running Arena:

```powershell
python scripts/student/preflight_observation_shadow_smoke.py `
  --scenario outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_train_r00_s91500.json `
  --episode-id pgrr_observation_shadow_leadstop_train_r00_20260913 `
  --output outputs/student/refactor_baseline/observation_shadow_smoke_preflight.json
```

Focused offline verification for the launcher/preflight gate:

```powershell
$env:PYTHONPATH=(Resolve-Path packages/ramp_core).Path
python -m pytest tests/unit/test_preflight_observation_shadow_smoke.py tests/unit/test_recovery_manager_observation_shadow_integration.py tests/unit/test_observation_shadow.py tests/unit/test_recovery_observation_builder.py tests/unit/test_verify_observation_builder_equivalence.py -q
python -m ruff check scripts/student/preflight_observation_shadow_smoke.py tests/unit/test_preflight_observation_shadow_smoke.py tests/unit/test_recovery_manager_observation_shadow_integration.py packages/ramp_core/ramp_core/recovery/observation_shadow.py packages/ramp_core/ramp_core/recovery/observation_builder.py scripts/student/verify_observation_builder_equivalence.py tests/unit/test_observation_shadow.py tests/unit/test_recovery_observation_builder.py tests/unit/test_verify_observation_builder_equivalence.py
```

After the future non-frozen smoke, validate its bounded shadow summary without
judging navigation performance:

```powershell
python scripts/student/validate_observation_shadow_smoke.py `
  --outcome data/raw/pgrr_observation_shadow_leadstop_train_r00_20260913.outcome.json `
  --runtime-log outputs/logs/baseline/pgrr_observation_shadow_leadstop_train_r00_20260913_runtime.log `
  --output outputs/student/refactor_baseline/observation_shadow_smoke_validation.json
```

Compare a checkout against the five source hashes pinned by the preflight (this
is read-only and exits nonzero on a missing or stale file):

```powershell
python scripts/student/verify_observation_shadow_runtime_sources.py `
  --manifest outputs/student/refactor_baseline/observation_shadow_smoke_preflight.json `
  --runtime-root . `
  --output outputs/student/refactor_baseline/observation_shadow_source_selfcheck.json
```

Synchronize only the five preflight-pinned runtime files with backup and LF
normalization (run from WSL; choose a new backup directory each time):

```bash
python3 /mnt/c/Users/28646/Documents/ChatGPT/New\ project/PGRR/scripts/student/sync_observation_shadow_runtime_sources.py \
  --manifest /mnt/c/Users/28646/Documents/ChatGPT/New\ project/PGRR/outputs/student/refactor_baseline/observation_shadow_smoke_preflight.json \
  --source-root /mnt/c/Users/28646/Documents/ChatGPT/New\ project/PGRR \
  --runtime-root /home/preface/PGRR-online \
  --backup-root /tmp/pgrr_observation_shadow_sync_backup_20260913_v2 \
  --output /tmp/pgrr_observation_shadow_sync_result.json
```

After Docker Desktop WSL integration is restored, verify the environment before
retrying the build:

```bash
docker version
cd ~/PGRR-online
make build
```

Re-run the default-off observation shadow comparator regression:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python -m pytest `
  tests/unit/test_observation_shadow.py `
  tests/unit/test_verify_observation_builder_equivalence.py `
  tests/unit/test_recovery_observation_builder.py -q
python scripts/student/verify_observation_builder_equivalence.py `
  --seed 92001 --cases 32 `
  --output outputs/student/refactor_baseline/observation_builder_equivalence.json
```

Check the default-off ROS observation-shadow integration and capture the
post-shadow structure without replacing the pre-shadow baseline:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python -m pytest `
  tests/unit/test_recovery_manager_observation_shadow_integration.py `
  tests/unit/test_observation_shadow.py `
  tests/unit/test_recovery_observation_builder.py `
  tests/unit/test_verify_observation_builder_equivalence.py -q
python scripts/student/audit_recovery_manager_structure.py `
  --output outputs/student/refactor_baseline/recovery_manager_structure_after_shadow.json
```

Verify the unused Homework 2 observation-builder prototype and the existing
observation/learning shape contract:

```powershell
$env:PYTHONPATH = @(
  (Resolve-Path packages/ramp_core).Path,
  (Resolve-Path packages/ramp_ml).Path
) -join ';'
python -m pytest `
  tests/unit/test_recovery_observation_builder.py `
  tests/unit/test_observations.py `
  tests/unit/test_ramp_ml.py -q
```

Regenerate the deterministic Homework 2 observation equivalence report:

```powershell
$env:PYTHONPATH = (Resolve-Path packages/ramp_core).Path
python scripts/student/verify_observation_builder_equivalence.py `
  --seed 92001 --cases 32 `
  --output outputs/student/refactor_baseline/observation_builder_equivalence.json
```

Audit trigger-path coverage in preserved non-frozen JSONL episodes (run where
the raw files live; the values are copied from checked-in configs):

```bash
python3 scripts/student/audit_trigger_coverage.py \
  data/raw/pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912_retry02.jsonl \
  data/raw/pgrr_masktrace_diagonal_train_r00_20260912.jsonl \
  data/raw/pgrr_masktrace_diagonal_validation_r00_20260912.jsonl \
  data/raw/pgrr_masktrace_headon_train_r00_20260912.jsonl \
  data/raw/pgrr_masktrace_headon_validation_r00_20260912.jsonl \
  --tau-on 0.65 --privileged-close-m 0.9 \
  --output outputs/student/eight_family_pilot/trigger_coverage_audit_20260912.json
```

Regenerate the read-only DAgger label/mask distribution audit with manifest
hash expectations:

```powershell
python scripts/student/analyze_dagger_label_mask_distribution.py `
  --dataset available_iter3_alias data/processed/dagger_coverage_train.h5 `
  --dataset later_iter5 data/processed/dagger_sequence_wait_aligned_train.h5 `
  --dataset available_validation_copy data/interim/multiscenario_safety_aligned_validation.h5 `
  --expected-sha256 available_iter3_alias d529efb4261f080b6ef06cb6bb7a3b90b3fb1d76e3008ea95398bf3b0c2f1948 `
  --expected-sha256 later_iter5 2a46403f914ec7403464778b13f99faa27fee475c31190b20cfc232f7f603522 `
  --expected-sha256 available_validation_copy 5d446cd01f7219b4adaf58e0661a4a5589077c7b4f8b6b3b21ef33d187331c92 `
  --output outputs/student/dagger_diagnostic/label_mask_distribution.json
```

Search current data and all local Git history for manifest-pinned DAgger HDF5
content hashes:

```powershell
python scripts/student/audit_dagger_manifest_artifacts.py `
  --manifest data/manifests/dagger_coverage_safety_aligned_manifest.json `
  --manifest data/manifests/dagger_sequence_wait_aligned_manifest.json `
  --output outputs/student/dagger_diagnostic/manifest_artifact_search.json
```

Run and validate the single preflighted non-frozen lead-stop validation smoke:

```bash
cd ~/PGRR-online
RAMP_SOURCE_POLICY=pgrr \
RAMP_ENABLE_UPSTREAM_MASK_TRACE=1 \
RAMP_EPISODE_ID=pgrr_masktrace_leadstop_validation_r00_20260912 \
RAMP_EPISODE_TIMEOUT_S=90 \
SCENARIO=outputs/student/eight_family_geometry_draft/generated/arena/map_empty/lead_pedestrian_sudden_stop_low_validation_r00_s93500.json \
scripts/arena/run_baseline_episode.sh
```

```powershell
python scripts/student/validate_mask_trace_smoke.py `
  --jsonl data/raw/pgrr_masktrace_leadstop_validation_r00_20260912.jsonl `
  --outcome data/raw/pgrr_masktrace_leadstop_validation_r00_20260912.outcome.json `
  --runtime-log outputs/logs/baseline/pgrr_masktrace_leadstop_validation_r00_20260912_runtime.log `
  --output outputs/student/eight_family_pilot/mask_trace_leadstop_validation_runtime_validation.json
```

Regenerate the hash-bound, non-causal timeout diagnosis and updated claim ledger:

```powershell
python scripts/student/diagnose_validation_timeout.py `
  --jsonl data/raw/pgrr_masktrace_leadstop_validation_r00_20260912.jsonl `
  --outcome data/raw/pgrr_masktrace_leadstop_validation_r00_20260912.outcome.json `
  --output outputs/student/eight_family_pilot/leadstop_validation_timeout_diagnosis.json

python scripts/student/build_extension_claim_ledger.py `
  --json-output outputs/student/paper_claim_ledger/extension_claim_ledger.json `
  --markdown-output outputs/student/paper_claim_ledger/extension_claim_ledger.md
```
