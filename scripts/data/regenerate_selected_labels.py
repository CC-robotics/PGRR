#!/usr/bin/env python3
"""Regenerate an explicit set of expert-label shards from a reviewed manifest."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    payload = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", [])
    if not jobs:
        raise ValueError("label manifest contains no jobs")
    for job in jobs:
        split = str(job["split"])
        if split not in {"train", "validation"}:
            raise ValueError(f"unsupported split: {split}")
        raw = ROOT / str(job["raw_jsonl"])
        output = ROOT / str(job["output_hdf5"])
        summary = ROOT / str(job["summary_json"])
        if not raw.is_file():
            raise FileNotFoundError(raw)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/data/label_expert.py"),
                str(raw),
                "--output",
                str(output),
                "--summary",
                str(summary),
            ],
            check=True,
        )
        print(f"regenerated split={split} output={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
