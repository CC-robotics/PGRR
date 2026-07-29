# Current status

## Gate 0 — environment (in progress)

### Completed

- Read-only host preflight: Ubuntu 22.04.5, 62 GiB RAM, 442 GiB free disk, RTX 5090, ROS2 Humble present.
- Created a new Git repository on `teacher/reference`; no pre-existing target files were overwritten.

### Commands

```bash
make preflight
make conda
```

### Acceptance results

- Host resource recommendations: PASS.
- ROS environment isolation: pending scripted verification.
- Arena smoke test: pending.

### Failures

- The invoking shell had Conda base active and ROS Iron selected. Runtime scripts must clear this and source Humble explicitly.

### Next

Create and validate `ramp-offline`, discover/install the compatible Arena profile, then run the headless smoke test.
