# Reproducing the PGRR final release

This document describes the single supported release of **PGRR:
Planning-Guided Failure-Triggered Recovery and Rejoin for Dynamic Social
Navigation**. Internal strings such as `moderate_social_navigation_v6` are
immutable benchmark/provenance identifiers, not separate product versions.
Historical `ramp_*` and `RAMP_*` names remain compatibility interfaces.

The published imitation-learning method consists of a privileged short-horizon
planning reference used only for labels, Uniform BC, two completed DAgger
rounds, an observable failure trigger, planning/action masks, bounded recovery
and rejoin, and an independent safety supervisor. The validation-selected
checkpoint is `checkpoints/final/best.onnx`. PPO and a learned failure detector
are not completed claims.

## Reproduction levels

| Level | Command | Starts simulation? | Paper evidence? |
|---|---|---:|---:|
| Tests | `make test` | no | no |
| Small contract check | `make reproduce-small` | no | no |
| Publication rebuild | `PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=0 scripts/reproduce_paper.sh` | no | yes |
| Clean release validation | `PGRR_RELEASE_MODE=1 PGRR_RECOLLECT_RAW=0 scripts/reproduce_paper.sh` | no | yes |
| Independent full rerun | `make evaluate-final` after calibration verification | yes | new evidence |

The existing final simulation is already complete. Most users should run the
publication rebuild or release validator, not the 600-episode evaluation.

## 1. Repository and environment boundary

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
git rev-parse HEAD
git status --short --branch
```

PGRR separates the online and offline environments:

- Online: Ubuntu 22.04, ROS2 Humble, pinned Arena Gazebo, Jackal, Nav2 DWB,
  planar LiDAR, Xvfb, and software rendering. Conda must be inactive.
- Offline: Python 3.10 Conda environment `ramp-offline` for data, labels,
  learning, statistics, figures, tests, and LaTeX. ROS must not be sourced.

```bash
make preflight
make conda
make arena
make build
```

Runtime provenance is pinned in `third_party/arena_commits.lock` and
`third_party/dependency_manifest.md`. Environment declarations are
`environment.yml`, `environment.lock.yml`, and
`requirements-offline.lock.txt`.

When directly invoking offline Python from a shell that may expose ROS, remove
foreign variables so the ROS `launch_testing` plugin cannot contaminate
pytest:

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

## 2. Tests and bounded runtime checks

```bash
make test
make smoke SEED=0 HEADLESS=1
make reproduce-small SEED=0
```

The smoke check verifies startup, cleanup, `/clock`, TF, LaserScan, odometry,
robot spawn, and Nav2 goal submission. Goal acceptance is not an algorithm
success. The small reproduction exercises schemas, masks, state machines,
expert labels, policy inference, and statistics on non-paper fixtures.

## 3. Frozen final inputs

The normative configuration is `configs/final/ei_gazebo.yaml`. Its release
dependencies are:

```text
configs/experiments/scenario_catalog_moderate_v6.yaml
scenarios/splits/moderate_v6_validation.yaml
scenarios/splits/moderate_v6_test.yaml
configs/planner/baselines.yaml
configs/failure/rules.yaml
configs/failure/recovery_state_machine.yaml
configs/planner/recovery_actions.yaml
checkpoints/bc/uniform_scenario/best.onnx
checkpoints/dagger/coverage_safety_aligned/best.onnx
outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json
```

The accepted calibration report has SHA-256
`0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f`.
The final configuration binds that value. Do not substitute
`outputs/moderate/final/calibration_report.json`; that possible untracked file
is an empty, rejected test-stage byproduct.

The held-out design is:

```text
8 families x 3 densities x 5 repeats = 120 conditions per method
120 conditions x 5 methods = 600 logical method--episodes
```

The methods are `base`, `standard`, `heuristic`, `bc_uniform`, and `pgrr`.
Every method uses the same 120 condition keys. Train, validation, and test are
split by scenario and seed, never by frame.

## 4. Published final result

The authoritative directory is `outputs/moderate/final/`. Run
`95ec74c511bb` records 600/600 logical outcomes at evaluation commit
`6916e7cd586acfbe200045e49b093039e2a6980e`:

| Method | Goal | Collision | Timeout | Planner failure |
|---|---:|---:|---:|---:|
| Base DWB | 85 | 35 | 0 | 0 |
| Standard | 81 | 39 | 0 | 0 |
| Heuristic | 100 | 1 | 6 | 13 |
| Uniform BC | 104 | 1 | 5 | 10 |
| PGRR | 109 | 0 | 2 | 9 |

The collector retains every algorithm outcome and all technical provenance.
The run has 614 outcome-bearing physical attempts: 600 algorithm outcomes,
eight excluded `SIMULATOR_FAILURE` attempts, and six excluded `INVALID_RESET`
attempts. Two attempt snapshots also preserve 42 no-outcome launch commands
over 39 unique tasks. Resumes ran only incomplete tasks and did not replace an
algorithm failure.

## 5. Rebuild documents from published evidence

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
```

This is the normal reproduction path. It does not launch Arena and does not
read `data/raw`. It verifies the published result, statistics, failure
analysis, matched evidence, telemetry media, and offline ablation; regenerates
result-dependent assets; builds all documents; and writes a candidate manifest.

Required final document outputs are:

- `paper/main.pdf`: exactly 8 pages;
- `report/PGRR_technical_report_zh.pdf`: exactly 32 pages;
- `presentation/PGRR_report_zh.pptx` and PDF: exactly 30 slides/pages.

Maintainers with the unpublished raw JSONL streams may explicitly recollect the
already completed episodes before rebuilding:

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=1 \
scripts/reproduce_paper.sh
```

Raw recollection does not run simulation. It reconstructs final Parquet/JSON
artifacts from episode streams and fails unless all task, scenario, commit,
terminal, and hash checks pass.

The builders refuse validation, pilot, smoke, calibration, live output, and
historical directories as final inputs. They require 600 rows, five methods,
120 complete paired conditions per method, the exact frozen split identity,
and a single evaluation commit.

## 6. Clean-checkout release validation

Commit the complete candidate bundle, then validate from a clean checkout:

```bash
test -z "$(git status --porcelain --untracked-files=all)"
PGRR_RELEASE_MODE=1 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
test -z "$(git status --porcelain --untracked-files=all)"
```

Release mode is validate-only. It independently reconstructs the manifest and
compares:

- all 96 required paths, sizes, and SHA-256 values;
- evaluation and generation provenance;
- the accepted calibration and frozen test split;
- result, statistics, raw-sidecar, screenshot, window, and telemetry bindings;
- 8/32/30 document page counts, final paper text, report/PPT data structure,
  and canonical media hashes;
- tracked and non-ignored privacy-sensitive content.

It must not modify the checkout. Font embedding and full document visual gates
run during the development build; release mode then verifies the hashes of
those accepted PDFs rather than rerunning the document generators.

## 7. Intentional full evaluation rerun

Do this only to create a new independent reproduction of the simulation, not to
rebuild the existing paper. Start from a clean worktree at the frozen
evaluation commit, verify the pinned runtime, confirm no Arena containers are
running, and choose a new output directory:

```bash
git worktree add ../PGRR-evaluation-reproduction \
  6916e7cd586acfbe200045e49b093039e2a6980e
cd ../PGRR-evaluation-reproduction
make verify-calibration
test ! -e outputs/moderate/independent_reproduction
make evaluate-final \
  MODERATE_ANALYSIS_DIR=outputs/moderate/independent_reproduction
```

The target runs all five methods with the committed held-out split, 240 s
horizon, and six parallel workers. The runner refuses to overwrite an existing
manifest. If infrastructure interruption leaves tasks incomplete, resume with
the same commit, inputs, and concurrency.

Terminal policy is fail-closed:

- `GOAL_REACHED`, `COLLISION`, `TIMEOUT`, and `PLANNER_FAILURE` are algorithm
  outcomes and are never retried;
- only `SIMULATOR_FAILURE` and `INVALID_RESET` are retryable, at most twice;
- every physical attempt remains in provenance;
- collection fails until every logical task has exactly one accepted algorithm
  outcome.

## 8. Statistical policy

The 120 conditions are paired across methods. Goal, collision, and timeout use
exact paired comparisons. All preregistered hypotheses across comparators and
endpoints enter one global Holm family. `PLANNER_FAILURE` remains a separate
descriptive terminal class with no post-hoc significance test. Duration and
path-length comparisons use only joint-success pairs and disclose that
conditioning.

Every number in the paper, report, and slides is generated from checked-in
Parquet, JSON, or CSV. Manual editing of numerical macros, tables, plots, or
slide values is forbidden.

## 9. Runtime image and telemetry policy

The real Gazebo GUI image at
`outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png` is bound to its
pixel SHA, scenario, terminal record, runtime, project/Arena commits, and window
metadata. It is a real historical moderate-v5 validation environment capture
(benchmark provenance, not another current release), not a camera frame from
the locked statistical run.

The matched trajectory and recovery timeline under
`outputs/moderate/final/media/` are generated from a real identical-condition
Base--PGRR held-out pair and bind to raw and result hashes. They are telemetry
reconstructions, not camera screenshots. Neither form of evidence may be
relabelled.

## 10. Authoritative outputs

```text
outputs/moderate/final/episode_manifest.parquet
outputs/moderate/final/run_manifest.json
outputs/moderate/final/results.parquet
outputs/moderate/final/summary.csv
outputs/moderate/final/pairwise_statistics.json
outputs/moderate/final/failure_analysis.md
outputs/moderate/final/matched_base_pgrr_evidence.json
outputs/moderate/final/offline_policy_ablation.csv
outputs/moderate/final/offline_policy_ablation.json
outputs/moderate/final/media/
outputs/moderate/final/artifact_manifest.json
outputs/figures/moderate_*.pdf
outputs/tables/moderate_*.tex
paper/generated/moderate_*.tex
paper/figures/moderate_*.pdf
paper/main.pdf
report/PGRR_technical_report_zh.pdf
presentation/PGRR_report_zh.pptx
presentation/PGRR_report_zh.pdf
```

The artifact manifest is the final authority for the exact release set.

## 11. No test-set tuning

The held-out test is open only as a frozen reported dataset. Its outcomes must
not influence the current algorithm, checkpoint, thresholds, scenarios,
metrics, representative-pair selector, or retry policy. Any such change needs
a new preregistered study with new scenario IDs and seed blocks. Failed
episodes may not be filtered, replaced, or converted into infrastructure
failures.

## 12. Historical audit boundary

One earlier frozen 64/64 audit is retained to keep the release honest:
PGRR/Base collisions were 0/24 versus 19/24, timeouts were 16/24 versus 0/24,
and goal reaches were 8/24 versus 5/24; the adjusted goal-reaching comparison
was not significant. This is historical v1 evidence, never a moderate-v6 input
or final result.

A later benchmark candidate was rejected before test because complete Base
validation reached 57/72 goals (79.17%), above the preregistered 75% ceiling.
The final benchmark retained its geometry, changed only Crossing Flow timing
using validation evidence, used fresh split seeds, and passed the unchanged
calibration before the test was opened. These facts defend against test-driven
benchmark tuning; they are not separate maintained releases.

## 13. Reproducibility limits

- The pinned Arena Humble fallback uses deterministic cylindrical pedestrian
  proxies, not validated human-intent dynamics.
- Evaluation uses one known map family, one planner, simulation localization,
  and planar LiDAR.
- Gazebo scheduling and startup can require classified infrastructure retries;
  all such attempts are retained.
- Raw JSONL streams are large and not part of the default Git checkout; the
  published Parquet/JSON artifacts and matched-evidence sidecars bind their
  relevant hashes.
- There is no hardware, second-planner, cross-simulator, human-subject, PPO,
  learned-detector, or formal-safety claim.

## 14. Publishing `main` and `home`

After the clean release gate passes, push the exact release commit to `home`,
merge that commit into `main` without rewriting history, rerun release mode on
the merge, and push `main`. Both remote branches must contain the same final
project release. Never force-push published evidence.
