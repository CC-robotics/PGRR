#!/usr/bin/env python3
"""Merge episode HDF5 shards without allowing temporal stacks to cross episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    observation_parts: dict[str, list[np.ndarray]] = {}
    label_parts: dict[str, list[np.ndarray]] = {}
    sample_indices: list[np.ndarray] = []
    sources: list[str] = []
    offset = 0
    for path in args.inputs:
        with h5py.File(path, "r") as handle:
            observation_length = len(handle["observations/lidar"])
            for name, dataset in handle["observations"].items():
                if name == "episode_start_index":
                    values = dataset[:].astype(np.int64) + offset
                else:
                    values = dataset[:]
                observation_parts.setdefault(name, []).append(values)
            for name, dataset in handle["labels"].items():
                label_parts.setdefault(name, []).append(dataset[:])
            sample_indices.append(handle["sample_index"][:] + offset)
            sources.append(str(handle.attrs["source_jsonl"]))
            offset += observation_length
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(args.output, "w") as output:
        output.attrs["schema_version"] = 1
        output.attrs["source_jsonl"] = json.dumps(sources)
        observations = output.create_group("observations")
        for name, parts in observation_parts.items():
            observations.create_dataset(name, data=np.concatenate(parts), compression="gzip")
        labels = output.create_group("labels")
        for name, parts in label_parts.items():
            labels.create_dataset(name, data=np.concatenate(parts), compression="gzip")
        output.create_dataset("sample_index", data=np.concatenate(sample_indices))
    print(f"Merged episodes={len(args.inputs)} observations={offset}")


if __name__ == "__main__":
    main()
