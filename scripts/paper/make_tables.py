#!/usr/bin/env python3
"""Generate LaTeX tables exclusively from recorded result artifacts."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    source = ROOT / "outputs/pilot/crossing_flow_medium_s02201_2164e08_pair.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        payload = list(csv.DictReader(stream))
    if [row["source_policy"] for row in payload] != ["base", "bc"]:
        raise RuntimeError("expected one ordered Base/BC verified-pose pair")
    if len({row["project_commit"] for row in payload}) != 1:
        raise RuntimeError("paired episodes must come from one project commit")
    names = {"base": "Classical DWB", "bc": "Triggered DAgger"}
    rows = [
        f"{names[result['source_policy']]} & {result['outcome'].replace('_', ' ')} & "
        f"{float(result['sim_duration_s']):.1f} & "
        f"{float(result['actual_goal_distance_m']):.3f} & "
        f"{float(result['min_human_distance_m']):.3f} & "
        f"{int(result['recovery_actions'])} \\\\"
        for result in payload
    ]
    caption = (
        "Verified-pose medium crossing-flow validation pair. Goal distance and human clearance "
        "use Gazebo model feedback; this is single-seed execution evidence only."
    )
    table = (
        """% Generated from outputs/pilot/crossing_flow_medium_s02201_2164e08_pair.csv
\\begin{table}[t]
\\caption{__CAPTION__}
\\label{tab:corrected-pair}
\\centering
\\small
\\resizebox{\\columnwidth}{!}{%
\\begin{tabular}{llrrrr}
\\hline
Method & Outcome & Time [s] & $d_g^{\\mathrm{phys}}$ [m] & $d_{\\min}$ [m] & Recovery \\\\
\\hline
"""
        + "\n".join(rows)
        + """
\\hline
\\end{tabular}
}
\\end{table}
"""
    ).replace("__CAPTION__", caption)
    output = ROOT / "paper/generated/verified_actual_pose_pair.tex"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(table, encoding="utf-8")


if __name__ == "__main__":
    main()
