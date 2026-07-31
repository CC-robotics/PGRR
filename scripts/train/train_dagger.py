#!/usr/bin/env python3
"""Aggregate policy-visited expert shards and retrain one DAgger iteration."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--base-datasets", nargs="+", type=Path, required=True)
    parser.add_argument("--dagger-shards", nargs="+", type=Path, required=True)
    parser.add_argument("--validation-dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-output", type=Path)
    parser.add_argument("--checkpoint-output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.iteration <= 0:
        raise ValueError("DAgger iteration must be positive")
    inputs = [*args.base_datasets, *args.dagger_shards]
    for path in [*inputs, args.validation_dataset, args.config]:
        if not path.is_file():
            raise FileNotFoundError(path)
    dataset_output = args.dataset_output or (
        ROOT / f"data/processed/dagger_iter{args.iteration}_train.h5"
    )
    checkpoint_output = args.checkpoint_output or (
        ROOT / f"checkpoints/dagger/iter_{args.iteration}"
    )
    manifest = args.manifest or (ROOT / f"data/manifests/dagger_iter{args.iteration}_manifest.json")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/data/merge_expert_datasets.py"),
            *(str(path) for path in inputs),
            "--output",
            str(dataset_output),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/train/train_bc.py"),
            str(dataset_output),
            "--validation-dataset",
            str(args.validation_dataset),
            "--config",
            str(args.config),
            "--output",
            str(checkpoint_output),
        ],
        check=True,
    )
    with h5py.File(dataset_output, "r") as handle:
        sample_count = len(handle["sample_index"])
        observation_count = len(handle["observations/lidar"])
        episode_count = len(np.unique(handle["observations/episode_start_index"][:]))
    metrics = json.loads((checkpoint_output / "metrics.json").read_text(encoding="utf-8"))
    best = min(metrics["history"], key=lambda item: item["validation"]["loss"])
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    payload = {
        "schema_version": 1,
        "iteration": args.iteration,
        "project_commit": commit,
        "dataset": {
            "path": str(dataset_output),
            "sha256": _sha256(dataset_output),
            "observation_count": observation_count,
            "sample_count": sample_count,
            "episode_count": episode_count,
        },
        "base_datasets": [
            {"path": str(path), "sha256": _sha256(path)} for path in args.base_datasets
        ],
        "dagger_shards": [
            {"path": str(path), "sha256": _sha256(path)} for path in args.dagger_shards
        ],
        "validation_dataset": {
            "path": str(args.validation_dataset),
            "sha256": _sha256(args.validation_dataset),
        },
        "config": {"path": str(args.config), "sha256": _sha256(args.config)},
        "checkpoint": {
            "path": str(checkpoint_output / "best.onnx"),
            "sha256": _sha256(checkpoint_output / "best.onnx"),
        },
        "best_validation_epoch": best,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"DAgger iteration={args.iteration} episodes={episode_count} samples={sample_count} "
        f"manifest={manifest}"
    )


if __name__ == "__main__":
    main()
