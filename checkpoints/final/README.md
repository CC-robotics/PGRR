# Frozen PGRR checkpoint

This directory is the stable release entry point for the model used by the
locked 64-episode evaluation. The files are relative symbolic links to the
selected validation checkpoint in `checkpoints/dagger/coverage_safety_aligned`;
they do not duplicate model bytes.

- `best.onnx`: deployed ROS2 inference model.
- `best.ts`: TorchScript export.
- `best.pt`: PyTorch training checkpoint.
- `config.yaml`: selected training configuration.
- `metrics.json`: validation history and provenance.

The deployed ONNX SHA-256 is
`78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2`.
The immutable evaluation record remains
`outputs/final/run_manifest.json`.
