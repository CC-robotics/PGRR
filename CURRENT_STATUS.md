# Current status

## Gate 0 — environment (in progress)

### Completed

- Read-only host preflight: Ubuntu 22.04.5, 62 GiB RAM, 442 GiB free disk, RTX 5090, ROS2 Humble present.
- Created a new Git repository on `teacher/reference`; no pre-existing target files were overwritten.
- Created `ramp-offline` with Python 3.10 and dual dependency locks.
- Validated Torch 2.13.0 + CUDA 13.0 on the RTX 5090.
- Passed Ruff, formatting, mypy, and 2 offline unit tests.

### Commands

```bash
make preflight
make conda
```

### Acceptance results

- Host resource recommendations: PASS.
- ROS environment isolation: pending scripted verification.
- Offline environment isolation: PASS; inherited ROS Python paths are cleared and regression-tested.
- Arena smoke test: pending.

### Failures

- The invoking shell had Conda base active and ROS Iron selected. Runtime scripts must clear this and source Humble explicitly.
- Native Arena installation needs sudo and the official installer contains a broad `$HOME/.pyenv` removal; installation is running inside an isolated `runc` container.

### Next

Finish and pin the Arena Humble Docker profile, build the project ROS overlay, then run the headless Gazebo smoke test.
