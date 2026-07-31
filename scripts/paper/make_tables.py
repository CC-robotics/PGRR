#!/usr/bin/env python3
"""Generate LaTeX tables exclusively from recorded result artifacts."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    source = ROOT / "outputs/pilot/crossing_flow_density_confirmed_proxy_pairs.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        payload = list(csv.DictReader(stream))
    if [row["source_policy"] for row in payload] != ["base", "bc"] * 3:
        raise RuntimeError("expected three ordered Base/BC corrected-proxy pairs")
    names = {"base": "Classical DWB", "bc": "Triggered DAgger"}
    rows = [
        f"{result['scenario_id'].split('_')[2].title()} & "
        f"{names[result['source_policy']]} & {result['outcome'].replace('_', ' ')} & "
        f"{float(result['sim_duration_s']):.1f} & {float(result['progress_m']):.2f} & "
        f"{float(result['min_human_distance_m']):.3f} & "
        f"{int(result['recovery_actions'])} \\\\"
        for result in payload
    ]
    caption = (
        "Corrected-proxy crossing-flow validation precheck. One fixed validation seed is used "
        "per density; these six episodes are execution evidence, not a significance claim."
    )
    table = (
        """% Generated from outputs/pilot/crossing_flow_density_confirmed_proxy_pairs.csv
\\begin{table}[t]
\\caption{__CAPTION__}
\\label{tab:corrected-pair}
\\centering
\\small
\\resizebox{\\columnwidth}{!}{%
\\begin{tabular}{lllrrrr}
\\hline
Density & Method & Outcome & Time [s] & Progress [m] & $d_{\\min}$ [m] & Recovery \\\\
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
    output = ROOT / "paper/generated/corrected_density_pairs.tex"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(table, encoding="utf-8")


if __name__ == "__main__":
    main()
