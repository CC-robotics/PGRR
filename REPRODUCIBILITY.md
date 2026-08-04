# Reproducing PGRR

This document describes the reproducible release of **PGRR: Planning-Guided
Recovery and Rejoin**. Commands resolve the Git root at runtime and therefore
remain valid if the repository is cloned, moved, or renamed.

The paper's locked method is the imitation-learning version: a privileged
short-horizon expert, behavior cloning, and planning/action masks applied during
labeling and deployment.  The two-round DAgger workflow was completed, but the
second-round checkpoint was worse on validation and is retained as a negative
result.  The locked checkpoint extends the better first-round aggregate with a
train-split coverage shard. PPO and the learned failure detector are outside
the claimed release result.

## Reproduction levels

| Level | Command | Purpose | Paper evidence? |
|---|---|---|---:|
| Tests | `make test` | Lint, formatting, types, unit/integration/regression tests | no |
| Small reproduction | `make reproduce-small` | Run bounded expert/mask/schema/statistics contracts and replay frozen policies on the small validation artifact; rebuild the paper only when final evidence already exists | no |
| Generated paper artifacts | `make figures`, `make tables`, `make paper` | Rebuild plots, LaTeX tables, bibliography, and PDF from existing results | yes, if inputs are the locked final artifacts |
| Full evaluation | explicit 64-episode command below | Re-run the frozen test split and paired analysis | yes |

Smoke runs and the small reproduction verify software flow. They must never be
reported as final training or evaluation.

## 1. Establish the repository root

Every command in this guide begins from the checked-out Git root:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
```

Record the revision and verify that code/configuration changes are committed
before a locked evaluation:

```bash
git rev-parse HEAD
git status --short
git diff --exit-code
git diff --cached --exit-code
```

The final evaluator fingerprints the Git commit, scenario files, and selected
checkpoint. Do not run a paper evaluation from an uncommitted algorithm or
configuration state.

## 2. Environment boundary

PGRR deliberately uses two isolated environments.

### Offline environment

`ramp-offline` is a Python 3.10 Conda environment for datasets, expert labels,
BC/DAgger, testing, statistics, figures, tables, and Tectonic. It must not source
ROS setup files.

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
make preflight
make conda
```

The declarations and locks are:

- [environment.yml](environment.yml)
- [environment.lock.yml](environment.lock.yml)
- [requirements-offline.lock.txt](requirements-offline.lock.txt)

### ROS2/Arena runtime

The verified online profile is the isolated Arena ROS2 Humble/Gazebo container,
not Conda, Flatland, or Arena 5.0. It uses Jackal and Nav2 DWB. Build it only
from a shell with no active project Conda environment:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
conda deactivate 2>/dev/null || true
unset CONDA_PREFIX CONDA_DEFAULT_ENV VIRTUAL_ENV
make arena
make build
```

Exact runtime provenance is in
[`third_party/arena_commits.lock`](third_party/arena_commits.lock) and
[`third_party/dependency_manifest.md`](third_party/dependency_manifest.md).
Runtime scripts also remove foreign ROS variables before sourcing Humble; this
is necessary on hosts whose default shell has another ROS distribution active.

## 3. Tests and smoke validation

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
make test
make smoke SEED=0 HEADLESS=1
```

`make test` must return zero. The smoke test checks Gazebo startup, Jackal,
`/clock`, TF, LiDAR, odometry, goal submission, and clean bounded shutdown. It
does not establish an algorithm success rate.

## 4. Small end-to-end reproduction

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
make reproduce-small SEED=0
make figures
make tables
make paper
```

The small path runs targeted schema, action-mask, state-machine, expert,
statistics, and paper-contract tests, then replays the frozen models on the
small scenario-disjoint policy set.  That replay is written under
`outputs/smoke/` and never replaces the frozen offline ablation.  When a
complete final run manifest is already present, the command additionally
rebuilds the final analysis and manuscript from the recorded evidence; it does
not launch simulation or claim to retrain the submitted checkpoint.

## 5. Frozen inputs for the paper evaluation

The normative experiment declaration is
[`configs/final/ei_gazebo.yaml`](configs/final/ei_gazebo.yaml). Before launching,
verify at least the following inputs and retain their hashes with the run:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

sha256sum \
  configs/final/ei_gazebo.yaml \
  scenarios/splits/test.yaml \
  checkpoints/dagger/coverage_safety_aligned/best.onnx \
  configs/failure/rules.yaml \
  configs/failure/recovery_state_machine.yaml \
  configs/planner/recovery_actions.yaml
```

The checkpoint expected by the frozen configuration is available through the
stable release entry point
[`checkpoints/final/best.onnx`](checkpoints/final/best.onnx), a relative link to
`checkpoints/dagger/coverage_safety_aligned/best.onnx`.
Its public method name is **Triggered-DAgger**. The runner retains the internal
method identifier `bc` for compatibility with ROS launch files, raw logs, and
older checkpoints.

The test split contains 24 immutable scenarios:

```text
8 families x 3 densities = 24 scenarios
24 x (Base DWB + Triggered-DAgger) = 48 logical episodes
8 high-density x (Standard + Heuristic) = 16 logical episodes
Total = 64 logical episodes
```

All methods use the same scenario records. A retry caused by
`SIMULATOR_FAILURE` or `INVALID_RESET` is a separately retained physical
attempt, not an extra algorithm sample.

## 6. Complete locked 64-episode evaluation

Run this once, after the configuration is frozen and before inspecting any test
outcome for tuning:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

env \
  -u PYTHONPATH \
  -u AMENT_PREFIX_PATH \
  -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH \
  -u ROS_DISTRO \
  -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  conda run -n ramp-offline \
  python scripts/evaluate/run_experiment.py \
    --split test \
    --methods base bc \
    --high-density-methods standard heuristic \
    --jobs 4 \
    --timeout 180 \
    --checkpoint checkpoints/dagger/coverage_safety_aligned/best.onnx \
    --output-dir outputs/final
```

The four workers receive distinct fixed ROS domain IDs and Gazebo partitions.
Use fewer `--jobs` on constrained systems; changing parallelism does not change
the logical manifest, but it must be recorded in `run_manifest.json`. Do not run
two evaluators with overlapping ROS domain ranges on the same host.

The runner refuses to overwrite an existing raw episode or locked manifest. If
the process is interrupted, use the **same commit, checkpoint, split, methods,
timeout, and output directory**, adding only `--resume`:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

env \
  -u PYTHONPATH \
  -u AMENT_PREFIX_PATH \
  -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH \
  -u ROS_DISTRO \
  -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  conda run -n ramp-offline \
  python scripts/evaluate/run_experiment.py \
    --split test \
    --methods base bc \
    --high-density-methods standard heuristic \
    --jobs 4 \
    --timeout 180 \
    --checkpoint checkpoints/dagger/coverage_safety_aligned/best.onnx \
    --output-dir outputs/final \
    --resume
```

Resume validates existing artifacts and only continues an incomplete logical
task. A logical task gets at most one retry, and only after an explicitly
classified `SIMULATOR_FAILURE` or `INVALID_RESET`. `GOAL_REACHED`, `COLLISION`,
`TIMEOUT`, and `PLANNER_FAILURE` are retained algorithm outcomes and are never
rerun merely because the result is unfavorable.

To independently reproduce published artifacts after `outputs/final/` and
`data/raw/` have already been populated, use a fresh checkout/worktree at the
recorded commit. Do not delete or overwrite the published raw evidence.

## 7. Collect results and run paired statistics

After the runner reports all 64 logical tasks complete:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

env \
  -u PYTHONPATH \
  -u AMENT_PREFIX_PATH \
  -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH \
  -u ROS_DISTRO \
  -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  conda run -n ramp-offline \
  python scripts/evaluate/collect_results.py \
    --manifest outputs/final/episode_manifest.parquet \
    --raw-dir data/raw \
    --run-manifest outputs/final/run_manifest.json \
    --results outputs/final/results.parquet \
    --summary outputs/final/summary.csv \
    --statistics outputs/final/statistics.json \
    --reference-policy base \
    --treatment-policy bc \
    --bootstrap-samples 10000 \
    --bootstrap-seed 20260804
```

Collection verifies manifest membership, completion, outcomes, and raw evidence
before writing derived files. The statistical unit is the paired scenario
episode. Reported analysis includes descriptive statistics, 95% paired bootstrap
confidence intervals, McNemar tests for binary outcomes, Wilcoxon signed-rank
tests for continuous metrics, effect sizes, and Holm multiple-comparison
correction. A p-value without its effect size and interval is incomplete.

The authoritative machine-readable outputs are:

- [episode manifest](outputs/final/episode_manifest.parquet)
- [run manifest](outputs/final/run_manifest.json)
- [episode results](outputs/final/results.parquet)
- [summary CSV](outputs/final/summary.csv)
- [statistics JSON](outputs/final/statistics.json)
- [failure analysis](outputs/final/failure_analysis.md)

If `summary.csv` or `statistics.json` is absent, do not substitute pilot values
or manually fill the paper tables.

## 8. Figures, tables, and manuscript

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

make figures
make tables
make paper
```

`make figures` and `make tables` read the locked summary/statistics files.
`make paper` regenerates those assets and compiles
[`paper/main.tex`](paper/main.tex) with IEEEtran using `latexmk` when available
or Tectonic from `ramp-offline`. The build fails for unresolved references,
citations, an empty PDF, or overfull boxes.

For a complete release-level replay after final artifacts exist:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"
make reproduce-paper
```

The final PDF is [paper/main.pdf](paper/main.pdf). Claims must remain aligned
with [`paper/claim_evidence_matrix.md`](paper/claim_evidence_matrix.md).

## 9. Required release checks

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

make test
make reproduce-small SEED=0
make figures
make tables
make paper

test -s outputs/final/episode_manifest.parquet
test -s outputs/final/run_manifest.json
test -s outputs/final/results.parquet
test -s outputs/final/summary.csv
test -s outputs/final/statistics.json
test -s outputs/final/failure_analysis.md
test -s outputs/final/artifact_manifest.json
test -s paper/main.pdf
```

When present, verify the generated
[artifact manifest](outputs/final/artifact_manifest.json) against the checked-out
commit and file hashes. `paper/main.pdf`, tables, and plots are derived; raw
episode streams, manifests, configuration, and checkpoint hashes are the
primary evidence.

## 10. No test-set tuning

The following protocol is mandatory:

1. Train only with scenarios in `scenarios/splits/train.yaml`.
2. Select architectures, thresholds, masks, rewards, checkpoints, and stopping
   rules only with the train and validation splits.
3. Freeze and commit the final configuration and record all hashes before the
   first test launch.
4. Execute every method against the same locked test manifest.
5. Retain all algorithm outcomes, including collisions, timeouts, and planner
   failures.
6. Exclude only `SIMULATOR_FAILURE` and `INVALID_RESET`, while reporting their
   counts, attempts, and reasons.
7. Never alter parameters after reading test outcomes. If a genuine software
   bug invalidates an episode, commit the fix, document it, and rerun every
   method affected by that bug under a newly versioned evaluation.

The test split is evidence, not a debugging curriculum. Development pilots and
counterexamples remain useful in `outputs/pilot/`, but they cannot be pooled
with the locked test or presented as independent final episodes.

## 11. Outcome and retry semantics

Every episode terminates in exactly one declared category:

- `GOAL_REACHED`
- `COLLISION`
- `TIMEOUT`
- `PLANNER_FAILURE`
- `SIMULATOR_FAILURE`
- `INVALID_RESET`

The first four are algorithm outcomes. The last two are infrastructure outcomes
and may receive one bounded retry. Raw `.jsonl`, `.metadata.json`, and
`.outcome.json` files are preserved so exclusions and retries remain auditable.

## 12. Known reproducibility limits

- The containerized Humble/Gazebo fallback differs from Arena 5.0, Flatland,
  real pedestrians, and hardware.
- Software rendering and Gazebo scheduling can change wall-clock duration even
  when scenario seeds are fixed; simulator time and outcome evidence are used
  for metrics.
- Fallback pedestrians are LiDAR-visible contactless actors, not a validated
  human-dynamics model.
- Pose-derived simulation localization is more accurate than a real localization
  pipeline.
- The expert depends on privileged simulator truth during label generation, but
  deployment inputs are observable only.
- The finite recovery action set and empirical safety margins provide no formal
  completeness or collision-avoidance guarantee.

For current problems and retained negative results, see
[CURRENT_STATUS.md](CURRENT_STATUS.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md), and
[DECISIONS.md](DECISIONS.md).
