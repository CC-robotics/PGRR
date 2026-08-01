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


def cross_family_pilot() -> None:
    sources = [
        ROOT / "outputs/pilot/temporary_blockage_high_s02720_0205d6e_pair.csv",
        ROOT / "outputs/pilot/group_blocking_high_s02420_926cc95_pair.csv",
        ROOT / "outputs/pilot/overtaking_high_s02520_324fcdf_pair.csv",
    ]
    pairs: list[list[dict[str, str]]] = []
    for source in sources:
        with source.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if [row["source_policy"] for row in rows] != ["base", "bc"]:
            raise RuntimeError(f"expected an ordered Base/BC pair in {source}")
        if len({row["project_commit"] for row in rows}) != 1:
            raise RuntimeError(f"pair must come from one project commit: {source}")
        pairs.append(rows)

    scenarios = ["TB", "GB", "OT"]
    methods = ["DWB", "Full hierarchy"]
    colors = ["#466B9F", "#16836B"]
    hatches = ["//", ""]
    # Use a short visible bar for the lower categorical outcome so the DWB
    # collision observations remain visible in print rather than collapsing
    # onto the axis baseline.
    outcome_score = {"COLLISION": 0.08, "GOAL_REACHED": 1.0}
    x = np.arange(len(scenarios), dtype=float)
    width = 0.34
    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axes = plt.subplots(1, 2, figsize=(3.45, 2.1), constrained_layout=True)
    for method_index, method in enumerate(methods):
        offset = (method_index - 0.5) * width
        selected = [pair[method_index] for pair in pairs]
        axes[0].bar(
            x + offset,
            [outcome_score[row["outcome"]] for row in selected],
            width=width,
            color=colors[method_index],
            hatch=hatches[method_index],
            label=method,
        )
        axes[1].bar(
            x + offset,
            [float(row["min_human_distance_m"]) for row in selected],
            width=width,
            color=colors[method_index],
            hatch=hatches[method_index],
        )
    axes[0].set_ylabel("Terminal outcome")
    axes[0].set_yticks([0.08, 1.0], ["Collision", "Goal"])
    axes[0].legend(
        frameon=False,
        fontsize=7,
        loc="lower center",
        ncol=2,
        bbox_to_anchor=(0.5, 1.01),
        borderaxespad=0.0,
    )
    axes[1].axhline(0.71, color="#D97706", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("Minimum human distance [m]")
    for axis in axes:
        axis.set_xticks(x, scenarios)
        axis.tick_params(axis="x", labelsize=6.5)
        axis.grid(axis="y", color="#D5DBDB", linewidth=0.6)
        axis.set_axisbelow(True)
    figure.savefig(
        ROOT / "paper/figures/cross_family_pilot.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def opposite_streams_ablation() -> None:
    source = ROOT / "outputs/pilot/opposite_streams_train_ablation.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [row["method"] for row in rows] != ["Iteration 4", "Turn memory", "Iteration 5"]:
        raise RuntimeError("unexpected opposite-stream ablation rows")
    if any(row["outcome"] != "TIMEOUT" for row in rows):
        raise RuntimeError("the retained failure analysis must contain all timeouts")

    labels = ["Iter. 4", "Turn\nmemory", "Iter. 5"]
    x = np.arange(len(rows), dtype=float)
    progress = np.asarray([float(row["net_progress_m"]) for row in rows])
    final_progress = np.asarray([float(row["last_60s_progress_m"]) for row in rows])
    samples = np.asarray([float(row["samples"]) for row in rows])
    emergency = np.asarray([float(row["emergency_samples"]) for row in rows]) / samples
    recovery = np.asarray([float(row["policy_recovery_samples"]) for row in rows]) / samples
    nominal = np.asarray([float(row["nominal_or_continue_samples"]) for row in rows]) / samples

    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axes = plt.subplots(1, 2, figsize=(3.45, 2.15), constrained_layout=True)
    colors = ["#16836B" if value >= 0.0 else "#D97706" for value in progress]
    axes[0].bar(x, progress, color=colors)
    axes[0].scatter(x, final_progress, marker="D", s=15, color="#202124", label="Final 60 s")
    axes[0].axhline(0.0, color="#555555", linewidth=0.7)
    axes[0].set_ylabel("Goal progress [m]")
    axes[0].legend(frameon=False, fontsize=6.5, loc="upper right")

    axes[1].bar(x, emergency, color="#D97706", label="Safety")
    axes[1].bar(x, recovery, bottom=emergency, color="#466B9F", label="Recovery")
    axes[1].bar(
        x,
        nominal,
        bottom=emergency + recovery,
        color="#D5DBDB",
        label="Continue/nominal",
    )
    axes[1].set_ylabel("Fraction of samples")
    axes[1].set_ylim(0.0, 1.0)
    axes[1].legend(
        frameon=False,
        fontsize=6.2,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=2,
        borderaxespad=0.0,
    )
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(axis="y", color="#E0E0E0", linewidth=0.6)
        axis.set_axisbelow(True)
    figure.savefig(
        ROOT / "paper/figures/opposite_streams_ablation.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def main() -> None:
    (ROOT / "paper/figures").mkdir(parents=True, exist_ok=True)
    architecture()
    verified_actual_pose_pair()
    high_density_pilot()
    cross_family_pilot()
    opposite_streams_ablation()


if __name__ == "__main__":
    main()
