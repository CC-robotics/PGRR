from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _module():  # type: ignore[no-untyped-def]
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "evaluate" / "summarize_gate2_pilot.py"
    spec = importlib.util.spec_from_file_location("summarize_gate2_pilot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, policy: str, outcomes: tuple[str, str]) -> None:
    fieldnames = (
        "episode_id",
        "scenario_id",
        "seed",
        "source_policy",
        "outcome",
        "progress_m",
        "min_human_distance_m",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for seed, outcome in enumerate(outcomes):
            writer.writerow(
                {
                    "episode_id": f"crossing_flow_high_mining_seed{seed:02d}_{policy}_dwb",
                    "scenario_id": f"crossing_flow_high_mining_seed{seed:02d}",
                    "seed": seed,
                    "source_policy": policy,
                    "outcome": outcome,
                    "progress_m": 1.0 + seed + (policy == "heuristic"),
                    "min_human_distance_m": 0.7,
                }
            )


def test_gate2_summary_pairs_by_scenario_and_seed(tmp_path: Path) -> None:
    module = _module()
    module.ROOT = tmp_path
    base = tmp_path / "base.csv"
    heuristic = tmp_path / "heuristic.csv"
    _write(base, "base", ("COLLISION", "TIMEOUT"))
    standard = tmp_path / "standard.csv"
    _write(standard, "standard", ("TIMEOUT", "TIMEOUT"))
    _write(heuristic, "heuristic", ("TIMEOUT", "GOAL_REACHED"))
    payload = module.summarize(
        [base],
        [heuristic],
        tmp_path / "result.json",
        tmp_path / "result.csv",
        seed=3,
        bootstrap_samples=100,
        standard_paths=[standard],
    )
    assert payload["pair_count"] == 2
    assert payload["base"]["collision_rate"] == 0.5
    assert payload["heuristic"]["success_rate"] == 0.5
    assert payload["standard"]["collision_rate"] == 0.0
    assert (
        payload["paired_statistics"]["progress_difference_m_heuristic_minus_base"]["estimate"]
        == 1.0
    )
    assert payload["excluded_invalid_reset_count"] == 0
