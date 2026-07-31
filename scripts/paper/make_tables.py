#!/usr/bin/env python3
"""Generate LaTeX tables exclusively from recorded result artifacts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    source = ROOT / "outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows: list[str] = []
    names = {"base": "Classical DWB", "bc": "Triggered DAgger"}
    for key in ("base", "bc"):
        result = payload["methods"][key]
        outcomes = result["outcome_counts"]
        reached = int(outcomes.get("GOAL_REACHED", 0))
        collision = int(outcomes.get("COLLISION", 0))
        timeout = int(outcomes.get("TIMEOUT", 0))
        time = result["median_success_time_s"]
        time_text = "--" if time is None else f"{float(time):.1f}"
        rows.append(
            f"{names[key]} & {reached}/5 & {collision}/5 & {timeout}/5 & "
            f"{float(result['median_min_human_distance_m']):.3f} & {time_text} \\\\"
        )
    caption = (
        "Repeated high-density crossing-flow pilot. The same scenario seed is repeated to "
        "expose simulator scheduling variance; these data are not the final multi-seed "
        "evaluation."
    )
    table = (
        """% Generated from outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json
\\begin{table}[t]
\\caption{__CAPTION__}
\\label{tab:pilot}
\\centering
\\small
\\resizebox{\\columnwidth}{!}{%
\\begin{tabular}{lccccc}
\\hline
Method & Goal & Collision & Timeout & $d_{\\min}$ [m] & Time [s] \\\\
\\hline
"""
        + "\n".join(rows)
        + """
\\hline
\\end{tabular}
}
\\end{table}
"""
    )
    table = table.replace("__CAPTION__", caption)
    output = ROOT / "paper/generated/pilot_results.tex"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(table, encoding="utf-8")


if __name__ == "__main__":
    main()
