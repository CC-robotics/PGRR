# Reproducing PGRR

This document describes the moderate-v6 release of **PGRR: Planning-Guided
Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation**.
Commands resolve the Git root at runtime and remain valid after the repository
is moved or renamed. Historical `ramp_*`/`RAMP_*` identifiers remain compatibility
interfaces only.

The paper evaluates the imitation-learning method: a privileged short-horizon
planning reference, Uniform BC, a completed two-round DAgger workflow, an
observable failure trigger, planning/action masks, recovery rejoin, and an
independent safety supervisor. The validation-selected deployment checkpoint
extends the accepted DAgger aggregate with a train-only coverage shard; the
second-round candidate was evaluated but not selected. PPO and a learned
failure detector are not completed or claimed contributions.

## Reproduction levels

| Level | Command | Purpose | Paper evidence? |
|---|---|---|---:|
| Tests | `make test` | Lint, formatting, types, and automated tests | no |
| Small reproduction | `make reproduce-small` | Exercise bounded data/model/statistics contracts | no |
| Paper rebuild | `make reproduce-paper` | Rebuild all documents from published final evidence; raw recollection is opt-in | yes |
| Full evaluation | complete command below | Re-run 600 held-out method--episodes | yes |

Smoke, pilot, calibration, and validation runs verify software or select a
configuration. They are never substituted for held-out test evidence.

## Documentation layers and evidence stages

PGRR maintains three independently validated documents:

1. `paper/main.pdf`: concise anonymous IEEE conference manuscript;
2. `report/PGRR_technical_report_zh.pdf`: detailed Chinese technical report;
3. `presentation/PGRR_report_zh.pptx` and its PDF export: thirty-slide Chinese
   briefing, with `presentation/speaker_notes_zh.md` and a contact sheet.

The report and presentation use the same stage contract:

| Stage | Approved input | Meaning |
|---|---|---|
| `pending` | no results or statistics file | Method, runtime, and protocol only; numerical pages visibly pending |
| `validation` | immutable results, statistics, and matched-run sidecar under `outputs/report_inputs/validation/` | Selection evidence, always marked non-final |
| `test` | the same three sibling artifacts under `outputs/moderate/final/` | Locked held-out evidence after the complete test protocol |

Build the current data-free documents without opening any result Parquet:

```bash
REPORT_STAGE=pending make technical-report presentation
```

After the validation writer has exited and the complete result has passed its
collector checks, create a separate read-only reporting snapshot. Never point
the report builder at the live validation output directory:

```bash
mkdir -p outputs/report_inputs/validation
install -m 0444 \
  outputs/moderate/v6_validation/results.parquet \
  outputs/report_inputs/validation/results.parquet
install -m 0444 \
  outputs/moderate/v6_validation/pairwise_statistics.json \
  outputs/report_inputs/validation/pairwise_statistics.json
python scripts/report/build_matched_run_evidence.py \
  --stage validation \
  --results outputs/moderate/v6_validation/results.parquet \
  --raw-dir data/raw \
  --output outputs/moderate/v6_validation/matched_base_pgrr_evidence.json
install -m 0444 \
  outputs/moderate/v6_validation/matched_base_pgrr_evidence.json \
  outputs/report_inputs/validation/matched_base_pgrr_evidence.json

REPORT_STAGE=validation \
REPORT_RESULTS=outputs/report_inputs/validation/results.parquet \
REPORT_STATISTICS=outputs/report_inputs/validation/pairwise_statistics.json \
REPORT_MATCHED_EVIDENCE=outputs/report_inputs/validation/matched_base_pgrr_evidence.json \
make technical-report presentation
```

The locked test documents are generated only with:

```bash
REPORT_STAGE=test \
REPORT_RESULTS=outputs/moderate/final/results.parquet \
REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
REPORT_MATCHED_EVIDENCE=outputs/moderate/final/matched_base_pgrr_evidence.json \
make technical-report presentation
```

The input guard rejects the historical 64-episode result, pilot, calibration,
smoke, rejected v5, `outputs/moderate/v6_validation`, and every
`outputs/moderate/v6_validation_*` path before reading them. No old result can be used
as a fallback for a test report, presentation, paper table, or conclusion.

## 1. Establish the repository root

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
```

Before a locked evaluation, record the revision and ensure algorithm,
configuration, scenario, and checkpoint inputs are committed:

```bash
git rev-parse HEAD
git status --short
git diff --exit-code
git diff --cached --exit-code
```

The runner fingerprints the Git commit, split manifest, every compiled
scenario, and each selected learned checkpoint.

## 2. Environment boundary

PGRR deliberately separates online ROS execution from offline analysis.

### Offline environment

The `ramp-offline` Python 3.10 Conda environment is used for HDF5/Parquet data,
expert labels, BC/DAgger, tests, statistics, vector figures, LaTeX tables, and
paper compilation. It must not source ROS setup files.

```bash
make preflight
make conda
```

The declarations and locks are
[`environment.yml`](environment.yml),
[`environment.lock.yml`](environment.lock.yml), and
[`requirements-offline.lock.txt`](requirements-offline.lock.txt).

### ROS2/Arena runtime

The verified online profile is Ubuntu 22.04 with the isolated Arena ROS2
Humble/Gazebo container, Jackal, Nav2 DWB, and planar LiDAR. Seeded cylindrical
pedestrian proxies are deterministic simulator actors, not validated human
intent. It is not Conda, Flatland, Arena 5, a second planner, hardware, or a
formal-safety platform.

```bash
conda deactivate 2>/dev/null || true
unset CONDA_PREFIX CONDA_DEFAULT_ENV VIRTUAL_ENV
make arena
make build
```

Exact runtime provenance is recorded in
[`third_party/arena_commits.lock`](third_party/arena_commits.lock) and
[`third_party/dependency_manifest.md`](third_party/dependency_manifest.md).
Runtime scripts remove foreign ROS variables before sourcing Humble.

## 3. Tests and runtime smoke check

```bash
make test
make smoke SEED=0 HEADLESS=1
```

The smoke test checks Gazebo startup, Jackal spawning, `/clock`, TF, LiDAR,
odometry, goal submission, and bounded cleanup. Goal acceptance is not an
algorithm-success result.

## 4. Small reproduction

```bash
make reproduce-small SEED=0
```

This path exercises schema, mask, state-machine, expert, policy, and statistics
contracts on small non-paper artifacts. It neither retrains the submitted model
nor launches the 600-episode test.

## 5. Preregistered moderate-v6 inputs

The normative declaration is
[`configs/final/ei_gazebo.yaml`](configs/final/ei_gazebo.yaml). Verify its
inputs before the first held-out test episode:

```bash
sha256sum \
  configs/final/ei_gazebo.yaml \
  configs/experiments/scenario_catalog_moderate_v6.yaml \
  scenarios/splits/moderate_v6_validation.yaml \
  scenarios/splits/moderate_v6_test.yaml \
  checkpoints/bc/uniform_scenario/best.onnx \
  checkpoints/dagger/coverage_safety_aligned/best.onnx \
  configs/planner/baselines.yaml \
  configs/failure/rules.yaml \
  configs/failure/recovery_state_machine.yaml \
  configs/planner/recovery_actions.yaml
```

Moderate-v6 contains eight interaction families, three densities, and five
held-out repetitions per family--density cell:

```text
8 families x 3 densities x 5 repetitions = 120 conditions per method
120 x 5 methods = 600 logical method--episodes
```

The five methods are `base`, `standard`, `heuristic`, `bc_uniform`, and
`pgrr`. Every method uses the identical 120 condition keys.

Moderate-v5 is preserved as a rejected audit: its complete Base validation
reached 57/72 goals (79.17%), exceeding the preregistered 75% ceiling, so no v5
test was opened. V6 retains its static geometry, changes only the predeclared
Crossing Flow timing band based on v5 validation phasing evidence, and uses new
seed blocks. See [`CURRENT_STATUS.md`](CURRENT_STATUS.md) and
[`DECISIONS.md`](DECISIONS.md); never copy v5 rows into a v6 reporting snapshot.

The selected PGRR artifact is
`checkpoints/dagger/coverage_safety_aligned/best.onnx`. Its training set is the
accepted DAgger aggregate plus a head-on coverage shard collected exclusively
from the train split. The separately retained second-round candidate did not
pass validation selection and is not substituted into the test protocol.

## 6. Validation-only calibration and lock

Benchmark construction and method selection use only train/validation data.
The accepted calibration report must be generated from the complete v6
validation manifest before test execution:

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
  python scripts/evaluate/run_experiment.py \
    --split validation \
    --split-manifest scenarios/splits/moderate_v6_validation.yaml \
    --methods base standard heuristic bc_uniform pgrr \
    --jobs 6 \
    --timeout 240 \
    --output-dir outputs/moderate/v6_validation

make statistics \
  MODERATE_ANALYSIS_DIR=outputs/moderate/v6_validation
```

The authoritative calibration evidence is
`outputs/moderate/v6_validation/calibration_report.json`. The artifact builder
requires `split=validation`, `status=accepted`, and `passed=true`; a report
computed from test rows is rejected. After validation selection, freeze the
tree before opening the test split:

```bash
git tag -a pre-final-eval-v6 -m "Frozen moderate-v6 evaluation inputs"
```

## 7. Complete held-out evaluation

Run the test once after the validation-selected tree is frozen:

```bash
make evaluate-flatland \
  MODERATE_SPLIT_MANIFEST=scenarios/splits/moderate_v6_test.yaml \
  MODERATE_ANALYSIS_DIR=outputs/moderate/final \
  EVALUATION_JOBS=6 \
  EVALUATION_TIMEOUT_S=240
```

`evaluate-flatland` is a retained compatibility target name; the locked runtime
is Gazebo. The runner refuses to overwrite an existing manifest. If execution
is interrupted, use the same commit, split, method set, checkpoints, timeout,
and output directory, adding only `--resume` to the equivalent direct command:

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
  python scripts/evaluate/run_experiment.py \
    --split test \
    --split-manifest scenarios/splits/moderate_v6_test.yaml \
    --methods base standard heuristic bc_uniform pgrr \
    --jobs 6 \
    --timeout 240 \
    --output-dir outputs/moderate/final \
    --resume
```

A logical task receives at most three physical attempts: one initial attempt
and up to two retries, each permitted only after an explicitly classified
`SIMULATOR_FAILURE` or `INVALID_RESET`. Every physical attempt remains in the
artifacts. `GOAL_REACHED`, `COLLISION`, `TIMEOUT`, and `PLANNER_FAILURE` are
retained algorithm outcomes and are never rerun because the result is
unfavorable.

## 8. Statistics, figures, tables, and paper

After all 600 logical tasks are complete:

```bash
make statistics MODERATE_ANALYSIS_DIR=outputs/moderate/final
make figures MODERATE_ANALYSIS_DIR=outputs/moderate/final
make tables MODERATE_ANALYSIS_DIR=outputs/moderate/final
make paper MODERATE_ANALYSIS_DIR=outputs/moderate/final
python scripts/report/build_matched_run_evidence.py \
  --stage test \
  --results outputs/moderate/final/results.parquet \
  --raw-dir data/raw \
  --output outputs/moderate/final/matched_base_pgrr_evidence.json
REPORT_STAGE=test \
  REPORT_RESULTS=outputs/moderate/final/results.parquet \
  REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
  REPORT_MATCHED_EVIDENCE=outputs/moderate/final/matched_base_pgrr_evidence.json \
  make technical-report presentation
```

The matched evidence selector is fixed at doorway-bottleneck / medium /
replicate 0. The extractor verifies each Base/PGRR JSONL SHA against Parquet
before exporting trajectories and event timelines. These plots are telemetry
reconstructions, not simulator camera screenshots. Missing raw logs or a hash
mismatch blocks result-stage report and deck generation.

The collector verifies manifest membership, completion, outcome evidence, and
paired metadata. The moderate summarizer requires exactly the same 120
conditions for all five methods. It produces paired bootstrap intervals, exact
McNemar tests for binary outcomes, Wilcoxon signed-rank tests for continuous
metrics, effect sizes, and one global Holm correction family.

For a complete document rebuild from the published, privacy-safe evidence:

```bash
MODERATE_ANALYSIS_DIR=outputs/moderate/final \
MODERATE_CALIBRATION_REPORT=outputs/moderate/v6_validation/calibration_report.json \
PGRR_RELEASE_MODE=0 \
PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
```

This command never launches simulation and rejects every result source except
the locked `outputs/moderate/final` test run with 120 paired conditions per
method. With the default `PGRR_RECOLLECT_RAW=0`, it does not access `data/raw`:
it consumes the published results, statistics, failure analysis, telemetry
media, the hash-linked matched-run sidecar, offline-ablation CSV/JSON, and
tracked validation HDF5. It regenerates
figures and tables, verifies the anonymous IEEEtran paper at exactly 8 pages,
builds a 30--40-page test-stage Chinese technical report, and builds the
30-slide PPTX/PDF, speaker notes, and contact sheet. It records the actual report
page count and writes a checksummed candidate manifest.

Maintainers with the unpublished raw streams may explicitly recollect and
rerender the result-dependent artifacts:

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=1 scripts/reproduce_paper.sh
```

Commit the resulting candidate bundle before the release gate. From that clean
checkout, run:

```bash
PGRR_RELEASE_MODE=1 scripts/reproduce_paper.sh
```

Release mode is validate-only: before any generation command it recomputes the
manifest, compares scientific provenance plus every artifact path/category/
size/SHA256/page/media field with the published manifest, runs the
tracked/nonignored privacy audit, and exits. It intentionally ignores only the
candidate timestamp and assembly-commit bookkeeping so the development-build,
commit, clean-validation sequence is closed rather than self-invalidating.

## 9. Runtime screenshot policy

Publication charts and diagrams are generated as vector PDFs. The repository's
simulator screenshot is a real, audited frozen-v5 validation demonstration and
is never synthesized.
The validated capture command and provenance rules are documented in
[`docs/runtime_screenshots.md`](docs/runtime_screenshots.md). When present, the
paper-facing image is
`paper/figures/runtime_gazebo_doorway_bottleneck_medium.png`, paired with
`outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json`.
The artifact builder rejects an unpaired screenshot or metadata file. It is not
a camera frame from a locked v6 statistical episode. Spatial paths, keyframes,
and event plots produced from JSONL/Parquet are explicitly labelled telemetry
reconstructions and must not be described as camera screenshots.

## 10. Authoritative outputs

- `outputs/moderate/v6_validation/calibration_report.json`
- `outputs/moderate/final/episode_manifest.parquet`
- `outputs/moderate/final/run_manifest.json`
- `outputs/moderate/final/results.parquet`
- `outputs/moderate/final/summary.csv`
- `outputs/moderate/final/pairwise_statistics.json`
- `outputs/moderate/final/matched_base_pgrr_evidence.json`
- `outputs/moderate/final/failure_analysis.md`
- `outputs/moderate/final/artifact_manifest.json`
- `outputs/moderate/final/offline_policy_ablation.csv`
- `outputs/moderate/final/offline_policy_ablation.json`
- `outputs/moderate/final/media/pgrr_representative_telemetry_keyframes.pdf`
- `outputs/moderate/final/media/pgrr_representative_telemetry_keyframes.png`
- `outputs/moderate/final/media/pgrr_representative_telemetry.mp4`
- `paper/generated/moderate_*.tex`
- `paper/figures/moderate_*.pdf`
- `outputs/figures/moderate_*.pdf`
- `outputs/tables/moderate_*.tex`
- `paper/main.pdf`
- `report/PGRR_technical_report_zh.pdf`
- `presentation/PGRR_report_zh.pptx`
- `presentation/PGRR_report_zh.pdf`
- `presentation/speaker_notes_zh.md`
- `presentation/contact_sheet.png`
- `data/interim/multiscenario_safety_aligned_validation.h5`

If any complete-run artifact is absent, do not substitute pilot values or
manually edit a result table.

## 11. Required release checks

```bash
make test
make reproduce-small SEED=0
make figures MODERATE_ANALYSIS_DIR=outputs/moderate/final
make tables MODERATE_ANALYSIS_DIR=outputs/moderate/final
make paper MODERATE_ANALYSIS_DIR=outputs/moderate/final
REPORT_STAGE=test \
  REPORT_RESULTS=outputs/moderate/final/results.parquet \
  REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
  REPORT_MATCHED_EVIDENCE=outputs/moderate/final/matched_base_pgrr_evidence.json \
  make technical-report presentation
make privacy-check

test -s outputs/moderate/v6_validation/calibration_report.json
test -s outputs/moderate/final/episode_manifest.parquet
test -s outputs/moderate/final/run_manifest.json
test -s outputs/moderate/final/results.parquet
test -s outputs/moderate/final/summary.csv
test -s outputs/moderate/final/pairwise_statistics.json
test -s outputs/moderate/final/matched_base_pgrr_evidence.json
test -s outputs/moderate/final/failure_analysis.md
test -s outputs/moderate/final/artifact_manifest.json
test -s outputs/moderate/final/offline_policy_ablation.csv
test -s outputs/moderate/final/offline_policy_ablation.json
test -s data/interim/multiscenario_safety_aligned_validation.h5
test -s paper/main.pdf
test -s report/PGRR_technical_report_zh.pdf
test -s presentation/PGRR_report_zh.pptx
test -s presentation/PGRR_report_zh.pdf
test -s presentation/speaker_notes_zh.md
test -s presentation/contact_sheet.png
```

After those generated files and the candidate manifest are committed, create a
clean checkout and run the non-mutating release gate:

```bash
test -z "$(git status --porcelain --untracked-files=all)"
PGRR_RELEASE_MODE=1 scripts/reproduce_paper.sh
```

The final PDF must have no unresolved references/citations, overfull boxes,
Type 3 fonts, or unembedded fonts. Run the privacy audit from the exact release
checkout; do not weaken its allowlist to admit stale paths or metadata.

## 12. No test-set tuning

1. Preserve the selected checkpoint's recorded train-only provenance; v6
   validation and test rows may not be used for retraining.
2. Select thresholds, masks, checkpoints, and stopping rules only with train and
   validation evidence.
3. Freeze and tag code, configuration, scenarios, and checkpoints before the
   first test launch.
4. Execute every method on the same test manifest.
5. Retain collisions, timeouts, planner failures, and infrastructure attempts.
6. Exclude only `SIMULATOR_FAILURE` and `INVALID_RESET` according to the stated
   protocol, while reporting their counts and reasons.
7. Never change parameters after inspecting test outcomes. A genuine code bug
   requires a documented fix and complete rerun of every affected method under
   a new version.

## 13. Known reproducibility limits

- The pinned Humble/Gazebo fallback differs from Arena 5, Flatland, real
  pedestrians, and hardware.
- Software rendering and Gazebo scheduling can change wall-clock duration;
  simulator time and terminal evidence are used for metrics.
- Deterministic LiDAR-visible actors are not a validated human-intent model.
- Simulation localization is more accurate than a deployed localization stack.
- The expert uses privileged simulator state during label generation only.
- The finite action set and empirical safety margins provide no formal
  completeness or collision-avoidance guarantee.
- PPO, a learned failure detector, a second planner, Flatland evaluation,
  hardware experiments, and formal safety are not completed claims.

Current retained negative results and limitations are tracked in
[`CURRENT_STATUS.md`](CURRENT_STATUS.md),
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md), and
[`DECISIONS.md`](DECISIONS.md).

## 14. GitHub maintenance

After the sanitized initial publication, use pull requests for ordinary
changes and preserve every published evidence tag. A corrected evaluation must
use a new experiment ID and release tag; never replace a tagged result in place
or tune a method from its held-out outcome.

Before pushing a release:

1. rebuild all three documentation layers from the same approved stage;
2. run tests, artifact validation, and the privacy audit from a clean checkout;
3. confirm that document metadata contains no local account, hostname,
   absolute path, token, or real identity;
4. use anonymous paper authorship and only the Charles Chen alias where a
   report or presentation author is required;
5. review `presentation/contact_sheet.png` and the technical-report PDF;
6. publish large raw evidence separately with checksums rather than adding
   transient simulator logs to the default branch.

Generated numerical tables and slide values are outputs, not editing surfaces.
Change the authoritative Parquet/JSON input, preserve its hash and provenance,
and regenerate every dependent artifact.
