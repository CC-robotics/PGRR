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
the 76 declared artifact hashes and document page counts, runs the privacy
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

## Scientific boundary

The earlier 64/64 audit remains part of the record: PGRR/Base collisions were
0/24 versus 19/24, timeouts 16/24 versus 0/24, and goal reaches 8/24 versus
5/24; the adjusted goal-reaching comparison was not significant. Those rows
are not inputs to any command that builds the final 600-episode result.
