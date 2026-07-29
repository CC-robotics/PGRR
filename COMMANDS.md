# Command log

Commands are copied here when a gate is accepted. Raw command output is stored under `outputs/logs/`.

```bash
make preflight
make conda
make test
```

Validated offline environment:

```bash
make conda
make test
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  conda run -n ramp-offline python -c 'import torch; print(torch.cuda.is_available())'
```
