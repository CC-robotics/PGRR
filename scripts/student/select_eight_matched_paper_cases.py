#!/usr/bin/env python3
"""Select reproducible illustrative Base-fail/PGRR-success cases.

This is a read-only, post-evaluation case selector.  Its output is descriptive and
must not be used as a replacement for the preregistered aggregate statistics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
DENSITY_RANK = {"high": 0, "medium": 1, "low": 2}


def build_candidates(results: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "replicate",
        "seed",
        "source_policy",
        "outcome",
    ]
    frame = results.loc[results["source_policy"].isin(METHODS), cols].copy()
    wide = frame.pivot(
        index=["pair_id", "scenario_id", "family", "density", "replicate", "seed"],
        columns="source_policy",
        values="outcome",
    ).reset_index()
    eligible = wide[(wide["base"] != "GOAL_REACHED") & (wide["pgrr"] == "GOAL_REACHED")].copy()
    comparators = ["standard", "heuristic", "bc_uniform"]
    eligible["other_comparator_failure_count"] = sum(
        eligible[name].ne("GOAL_REACHED").astype(int) for name in comparators
    )
    eligible["density_rank"] = eligible["density"].map(DENSITY_RANK).fillna(9).astype(int)
    return eligible.sort_values(
        ["family", "other_comparator_failure_count", "density_rank", "replicate", "seed"],
        ascending=[True, False, True, True, True],
    ).reset_index(drop=True)


def select_cases(candidates: pd.DataFrame, count: int = 8) -> pd.DataFrame:
    if count < 1:
        raise ValueError("count must be positive")
    selected_indices: list[int] = []

    # First guarantee one representative from every family that actually contains
    # a discordant Base/PGRR pair.
    for _, group in candidates.groupby("family", sort=True):
        selected_indices.append(int(group.index[0]))

    # Then fill deterministically while limiting concentration to two cases per
    # family whenever enough families are available.
    family_counts = candidates.loc[selected_indices, "family"].value_counts().to_dict()
    remainder = candidates.drop(index=selected_indices).sort_values(
        ["other_comparator_failure_count", "density_rank", "family", "replicate", "seed"],
        ascending=[False, True, True, True, True],
    )
    for index, row in remainder.iterrows():
        if len(selected_indices) >= count:
            break
        family = str(row["family"])
        if family_counts.get(family, 0) >= 2:
            continue
        selected_indices.append(int(index))
        family_counts[family] = family_counts.get(family, 0) + 1

    if len(selected_indices) < count:
        for index in remainder.index:
            if len(selected_indices) >= count:
                break
            if int(index) not in selected_indices:
                selected_indices.append(int(index))

    if len(selected_indices) < count:
        raise ValueError(f"only {len(selected_indices)} eligible cases are available")

    selected = candidates.loc[selected_indices].copy()
    selected.insert(0, "case_number", range(1, len(selected) + 1))
    return selected.drop(columns=["density_rank"]).reset_index(drop=True)


def render_markdown(selected: pd.DataFrame, eligible_count: int, eligible_families: int) -> str:
    lines = [
        "# Eight matched qualitative case candidates",
        "",
        (
            f"The frozen 600-episode result contains {eligible_count} matched conditions "
            f"where Base did not reach and PGRR reached, spanning {eligible_families} "
            "of 8 families."
        ),
        (
            "The eight rows below are a deterministic, post-hoc qualitative subset; "
            "they are not eight independent statistical claims."
        ),
        "",
        (
            "| # | Family | Density | Rep | Seed | Base | Standard | Heuristic | "
            "Uniform BC | PGRR | Other failures |"
        ),
        "|---:|---|---|---:|---:|---|---|---|---|---|---:|",
    ]
    for row in selected.itertuples(index=False):
        lines.append(
            f"| {row.case_number} | `{row.family}` | {row.density} | {row.replicate} | "
            f"{row.seed} | {row.base} | {row.standard} | {row.heuristic} | "
            f"{row.bc_uniform} | {row.pgrr} | {row.other_comparator_failure_count} |"
        )
    lines += [
        "",
        (
            "Selection rule: require Base != GOAL_REACHED and PGRR = GOAL_REACHED; "
            "choose one per eligible family, then fill to eight by other-comparator "
            "failure count and difficulty, with at most two per family when possible."
        ),
        "",
        (
            "Boundary: this table may illustrate trajectories or failure mechanisms. "
            "Formal claims must continue to use all 120 paired conditions and the "
            "existing corrected statistics."
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, default=Path("outputs/moderate/final/results.parquet")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/student/paper_case_shortlist")
    )
    args = parser.parse_args()

    results = pd.read_parquet(args.results)
    candidates = build_candidates(results)
    selected = select_cases(candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output_dir / "eight_matched_cases.csv", index=False)
    payload = {
        "status": "post_hoc_qualitative_selection_only",
        "source": str(args.results).replace("\\", "/"),
        "eligible_pair_count": len(candidates),
        "eligible_family_count": int(candidates["family"].nunique()),
        "selected_case_count": len(selected),
        "selection_rule": (
            "Base non-goal and PGRR goal; one per eligible family, then comparator "
            "failures/difficulty, maximum two per family when possible"
        ),
        "cases": selected.to_dict(orient="records"),
    }
    (args.output_dir / "eight_matched_cases.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "eight_matched_cases.md").write_text(
        render_markdown(selected, len(candidates), candidates["family"].nunique()), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
