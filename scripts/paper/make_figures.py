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


def corrected_density_pairs() -> None:
    source = ROOT / "outputs/pilot/crossing_flow_density_confirmed_proxy_pairs.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [row["source_policy"] for row in rows] != ["base", "bc"] * 3:
        raise RuntimeError("expected three ordered Base/BC corrected-proxy pairs")
    densities = ["Low", "Medium", "High"]
    base = rows[::2]
    learned = rows[1::2]
    x = np.arange(len(densities))
    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axes = plt.subplots(1, 2, figsize=(3.45, 1.95), constrained_layout=True)
    axes[0].plot(x, [0.0] * 3, "o-", color="#466B9F", label="DWB: collision")
    axes[0].plot(x, [1.0] * 3, "s-", color="#16836B", label="DAgger: goal")
    axes[0].set_ylabel("Terminal outcome")
    axes[0].set_yticks([0.0, 1.0], ["Collision", "Goal"])
    axes[0].legend(frameon=False, fontsize=6, loc="center right")
    axes[1].plot(
        x,
        [float(row["min_human_distance_m"]) for row in base],
        "o-",
        color="#466B9F",
        label="DWB",
    )
    axes[1].plot(
        x,
        [float(row["min_human_distance_m"]) for row in learned],
        "s-",
        color="#16836B",
        label="DAgger",
    )
    axes[1].axhline(0.71, color="#D97706", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("Minimum human distance [m]")
    axes[1].legend(frameon=False, fontsize=6)
    for axis in axes:
        axis.set_xticks(x, densities)
        axis.grid(axis="y", color="#D5DBDB", linewidth=0.6)
        axis.set_axisbelow(True)
    figure.savefig(
        ROOT / "paper/figures/corrected_density_pairs.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def main() -> None:
    (ROOT / "paper/figures").mkdir(parents=True, exist_ok=True)
    architecture()
    corrected_density_pairs()


if __name__ == "__main__":
    main()
