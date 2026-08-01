#!/usr/bin/env python3
"""Generate LaTeX tables exclusively from recorded result artifacts."""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def verified_actual_pose_pair() -> None:
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


def high_density_pilot() -> None:
    sources = [
        ROOT / "outputs/pilot/crossing_flow_high_s02201_8577ff1_pair.csv",
        ROOT / "outputs/pilot/crossing_flow_high_s02202_8577ff1_pair.csv",
        ROOT / "outputs/pilot/crossing_flow_high_s02220_8577ff1_pair.csv",
    ]
    results: dict[str, list[dict[str, str]]] = {"base": [], "bc": []}
    commits: set[str] = set()
    for source in sources:
        with source.open(encoding="utf-8", newline="") as stream:
            payload = list(csv.DictReader(stream))
        if [row["source_policy"] for row in payload] != ["base", "bc"]:
            raise RuntimeError(f"expected an ordered Base/BC pair in {source}")
        for row in payload:
            results[row["source_policy"]].append(row)
            commits.add(row["project_commit"])
    if len(commits) != 1:
        raise RuntimeError("high-density pilot episodes must come from one project commit")

    names = {"base": "Classical DWB", "bc": "Triggered DAgger"}
    rows = []
    episode_count = len(sources)
    for policy in ("base", "bc"):
        payload = results[policy]
        successes = sum(row["outcome"] == "GOAL_REACHED" for row in payload)
        collisions = sum(row["outcome"] == "COLLISION" for row in payload)
        median_time = statistics.median(float(row["sim_duration_s"]) for row in payload)
        median_clearance = statistics.median(float(row["min_human_distance_m"]) for row in payload)
        median_actions = statistics.median(int(row["recovery_actions"]) for row in payload)
        rows.append(
            f"{names[policy]} & {successes}/{episode_count} & {collisions}/{episode_count} & "
            f"{median_time:.1f} & "
            f"{median_clearance:.3f} & {median_actions:.1f} \\\\"
        )
    caption = (
        "High-density crossing-flow validation pilot on three fixed seeds. Values are "
        "descriptive medians; $n=3$ is insufficient for significance testing."
    )
    table = (
        """% Generated from three outputs/pilot/crossing_flow_high_*_8577ff1_pair.csv files
\\begin{table}[t]
\\caption{__CAPTION__}
\\label{tab:high-density-pilot}
\\centering
\\small
\\resizebox{\\columnwidth}{!}{%
\\begin{tabular}{lrrrrr}
\\hline
Method & Goal & Collision & Time [s] & $d_{\\min}$ [m] & Recovery \\\\
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
    (ROOT / "paper/generated/high_density_pilot.tex").write_text(table, encoding="utf-8")


def cross_family_pilot() -> None:
    sources = [
        (
            "Temporary blockage",
            ROOT / "outputs/pilot/temporary_blockage_high_s02720_0205d6e_pair.csv",
        ),
        (
            "Group blocking",
            ROOT / "outputs/pilot/group_blocking_high_s02420_dcd9bfe_pair.csv",
        ),
    ]
    rows: list[str] = []
    for scenario, source in sources:
        with source.open(encoding="utf-8", newline="") as stream:
            payload = list(csv.DictReader(stream))
        if [row["source_policy"] for row in payload] != ["base", "bc"]:
            raise RuntimeError(f"expected an ordered Base/BC pair in {source}")
        if len({row["project_commit"] for row in payload}) != 1:
            raise RuntimeError(f"pair must come from one project commit: {source}")
        base, recovery = payload
        rows.append(
            f"{scenario} & {base['outcome'].replace('_', ' ')} & "
            f"{recovery['outcome'].replace('_', ' ')} & "
            f"{float(base['sim_duration_s']):.1f}/{float(recovery['sim_duration_s']):.1f} & "
            f"{float(base['min_human_distance_m']):.3f}/"
            f"{float(recovery['min_human_distance_m']):.3f} & "
            f"{int(recovery['recovery_actions'])} \\\\"
        )
    caption = (
        "Cross-family high-density validation examples (DWB/full hierarchy). Each row is one "
        "internally same-commit pair; values are descriptive and are not pooled for inference."
    )
    table = (
        """% Generated from the temporary- and group-blocking pair CSV files
\\begin{table}[t]
\\caption{__CAPTION__}
\\label{tab:cross-family-pilot}
\\centering
\\small
\\resizebox{\\columnwidth}{!}{%
\\begin{tabular}{lllrrr}
\\hline
Scenario & DWB & Hierarchy & Time [s] & $d_{\\min}$ [m] & Recovery \\\\
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
    (ROOT / "paper/generated/cross_family_pilot.tex").write_text(table, encoding="utf-8")


def main() -> None:
    verified_actual_pose_pair()
    high_density_pilot()
    cross_family_pilot()


if __name__ == "__main__":
    main()
