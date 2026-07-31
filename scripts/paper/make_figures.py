#!/usr/bin/env python3
"""Generate reproducible vector figures from versioned result artifacts."""

from __future__ import annotations

import csv
import os
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def architecture() -> None:
    source = ROOT / "paper/figures/system_architecture.dot"
    output = ROOT / "paper/figures/system_architecture.pdf"
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = "0"
    subprocess.run(["dot", "-Tpdf", str(source), "-o", str(output)], check=True, env=environment)
    payload = output.read_bytes()
    payload, replacements = re.subn(
        rb"/CreationDate \(D:\d{14}[+-]\d{2}'\d{2}\)",
        rb"/CreationDate (D:19700101000000+00'00)",
        payload,
    )
    if replacements != 1:
        raise RuntimeError("expected exactly one Graphviz PDF creation date")
    output.write_bytes(payload)


def verified_actual_pose_pair() -> None:
    source = ROOT / "outputs/pilot/crossing_flow_medium_s02201_2164e08_pair.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [row["source_policy"] for row in rows] != ["base", "bc"]:
        raise RuntimeError("expected one ordered Base/BC verified-pose pair")
    if len({row["project_commit"] for row in rows}) != 1:
        raise RuntimeError("paired episodes must come from one project commit")
    methods = ["DWB", "DAgger"]
    x = np.arange(len(methods))
    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axes = plt.subplots(1, 2, figsize=(3.45, 1.95), constrained_layout=True)
    outcome_score = {"COLLISION": 0.0, "GOAL_REACHED": 1.0}
    axes[0].bar(
        x,
        [outcome_score[row["outcome"]] for row in rows],
        color=["#466B9F", "#16836B"],
    )
    axes[0].set_ylabel("Terminal outcome")
    axes[0].set_yticks([0.0, 1.0], ["Collision", "Goal"])
    axes[1].bar(
        x,
        [float(row["min_human_distance_m"]) for row in rows],
        color=["#466B9F", "#16836B"],
    )
    axes[1].axhline(0.71, color="#D97706", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("Minimum human distance [m]")
    for axis in axes:
        axis.set_xticks(x, methods)
        axis.grid(axis="y", color="#D5DBDB", linewidth=0.6)
        axis.set_axisbelow(True)
    figure.savefig(
        ROOT / "paper/figures/verified_actual_pose_pair.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def high_density_pilot() -> None:
    sources = [
        ROOT / "outputs/pilot/crossing_flow_high_s02201_8577ff1_pair.csv",
        ROOT / "outputs/pilot/crossing_flow_high_s02202_8577ff1_pair.csv",
        ROOT / "outputs/pilot/crossing_flow_high_s02220_8577ff1_pair.csv",
    ]
    pairs: list[list[dict[str, str]]] = []
    for source in sources:
        with source.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if [row["source_policy"] for row in rows] != ["base", "bc"]:
            raise RuntimeError(f"expected an ordered Base/BC pair in {source}")
        pairs.append(rows)
    commits = {row["project_commit"] for pair in pairs for row in pair}
    if len(commits) != 1:
        raise RuntimeError("high-density pilot episodes must come from one project commit")

    methods = ["DWB", "Triggered\nDAgger"]
    colors = ["#466B9F", "#16836B"]
    offsets = [-0.24, 0.0, 0.24]
    hatches = ["", "//", "xx"]
    outcome_score = {"COLLISION": 0.0, "GOAL_REACHED": 1.0}
    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axes = plt.subplots(1, 2, figsize=(3.45, 2.05), constrained_layout=True)
    for seed_index, pair in enumerate(pairs):
        x = np.arange(len(methods), dtype=float) + offsets[seed_index]
        axes[0].bar(
            x,
            [outcome_score[row["outcome"]] for row in pair],
            width=0.22,
            color=colors,
            alpha=0.72 + 0.12 * seed_index,
            hatch=hatches[seed_index],
        )
        axes[1].bar(
            x,
            [float(row["min_human_distance_m"]) for row in pair],
            width=0.22,
            color=colors,
            alpha=0.72 + 0.12 * seed_index,
            hatch=hatches[seed_index],
        )
    axes[0].set_ylabel("Terminal outcome")
    axes[0].set_yticks([0.0, 1.0], ["Collision", "Goal"])
    axes[1].axhline(0.71, color="#D97706", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("Minimum human distance [m]")
    for axis in axes:
        axis.set_xticks(np.arange(len(methods)), methods)
        axis.grid(axis="y", color="#D5DBDB", linewidth=0.6)
        axis.set_axisbelow(True)
    figure.savefig(
        ROOT / "paper/figures/high_density_pilot.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def main() -> None:
    (ROOT / "paper/figures").mkdir(parents=True, exist_ok=True)
    architecture()
    verified_actual_pose_pair()
    high_density_pilot()


if __name__ == "__main__":
    main()
