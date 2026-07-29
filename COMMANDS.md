# Command log

Commands are copied here when a gate is accepted. Raw command output is stored under `outputs/logs/`.

```bash
make preflight
make conda
make arena
make smoke
make test
```

Validated offline environment:

```bash
make conda
make test
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  conda run -n ramp-offline python -c 'import torch; print(torch.cuda.is_available())'
```

Validated Arena runtime without activating Conda:

```bash
make arena
make smoke
scripts/bootstrap/arena_container.sh bash -lc \
  'ros2 pkg prefix arena_bringup; ros2 pkg prefix bondcpp; gz sim --versions'
```

The complete simulator and goal logs are written to `outputs/logs/arena_runtime.log` and `outputs/logs/arena_runtime_goal.log`; generated logs are intentionally not versioned.
