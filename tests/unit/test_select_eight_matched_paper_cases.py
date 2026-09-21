from __future__ import annotations

import pandas as pd

from scripts.student.select_eight_matched_paper_cases import build_candidates, select_cases


def _rows() -> pd.DataFrame:
    rows = []
    for family_index, family in enumerate(("a", "b", "c", "d", "e")):
        for replicate in range(2):
            pair = f"{family}_{replicate}"
            outcomes = {
                "base": "COLLISION",
                "standard": "COLLISION" if replicate == 0 else "GOAL_REACHED",
                "heuristic": "GOAL_REACHED",
                "bc_uniform": "GOAL_REACHED",
                "pgrr": "GOAL_REACHED",
            }
            for policy, outcome in outcomes.items():
                rows.append(
                    {
                        "pair_id": pair,
                        "scenario_id": pair,
                        "family": family,
                        "density": "high" if replicate == 0 else "low",
                        "replicate": replicate,
                        "seed": 100 + family_index * 10 + replicate,
                        "source_policy": policy,
                        "outcome": outcome,
                    }
                )
    return pd.DataFrame(rows)


def test_selector_covers_all_eligible_families_and_returns_eight() -> None:
    candidates = build_candidates(_rows())
    selected = select_cases(candidates, count=8)
    assert len(selected) == 8
    assert set(selected["family"]) == {"a", "b", "c", "d", "e"}
    assert selected["family"].value_counts().max() <= 2
    assert (selected["base"] != "GOAL_REACHED").all()
    assert (selected["pgrr"] == "GOAL_REACHED").all()


def test_selector_prefers_more_failed_other_comparators_per_family() -> None:
    selected = select_cases(build_candidates(_rows()), count=5)
    assert set(selected["replicate"]) == {0}
    assert set(selected["other_comparator_failure_count"]) == {1}
