#!/usr/bin/env python3
"""Generate reproducible vector figures from versioned sources and pilot results."""

from __future__ import annotations

import json
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
    subprocess.run(
        ["dot", "-Tpdf", str(source), "-o", str(output)],
        check=True,
        env=environment,
    )
    # Cairo 1.16 ignores SOURCE_DATE_EPOCH and writes wall-clock metadata.
    # The fixed-width replacement leaves PDF object offsets unchanged.
    payload = output.read_bytes()
    payload, replacements = re.subn(
        rb"/CreationDate \(D:\d{14}[+-]\d{2}'\d{2}\)",
        rb"/CreationDate (D:19700101000000+00'00)",
        payload,
    )
    if replacements != 1:
        raise RuntimeError("expected exactly one Graphviz PDF creation date")
    output.write_bytes(payload)


def pilot_outcomes() -> None:
    summary = json.loads(
        (ROOT / "outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json").read_text()
    )
    methods = ["Classical DWB", "Failure-triggered DAgger"]
    keys = ["base", "bc"]
    success = [summary["methods"][key]["success_rate"] for key in keys]
    collision = [summary["methods"][key]["collision_rate"] for key in keys]
    x = np.arange(len(methods))
    width = 0.32
    plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})
    figure, axis = plt.subplots(figsize=(3.45, 2.15), constrained_layout=True)
    axis.bar(x - width / 2, success, width, label="Goal reached", color="#16836B")
    axis.bar(x + width / 2, collision, width, label="Collision", color="#D97706")
    axis.set_xticks(x, methods)
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("Episode rate")
    axis.grid(axis="y", color="#D5DBDB", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, ncols=2, loc="upper center")
    axis.text(
        0.5,
        -0.25,
        "Repeated same-seed pilot (5 episodes/method); not final significance evidence",
        transform=axis.transAxes,
        ha="center",
        va="top",
        fontsize=6.5,
    )
    figure.savefig(
        ROOT / "paper/figures/pilot_outcomes.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    plt.close(figure)


def main() -> None:
    (ROOT / "paper/figures").mkdir(parents=True, exist_ok=True)
    architecture()
    pilot_outcomes()


if __name__ == "__main__":
    main()
