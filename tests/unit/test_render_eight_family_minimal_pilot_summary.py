from __future__ import annotations

import json
from pathlib import Path

from scripts.student.render_eight_family_minimal_pilot_summary import summarize

ROOT = Path(__file__).resolve().parents[2]


def test_complete_pilot_aggregate_keeps_safety_completion_boundary() -> None:
    path = ROOT / "outputs/student/eight_family_pilot/minimal_pair_progress.json"
    summary = summarize(json.loads(path.read_text(encoding="utf-8")))
    aggregate = summary["aggregate"]

    assert aggregate["complete_pair_count"] == 8
    assert aggregate["valid_algorithm_episode_count"] == 16
    assert aggregate["preserved_infrastructure_attempt_count"] == 2
    assert aggregate["base_outcome_counts"] == {"COLLISION": 6, "TIMEOUT": 2}
    assert aggregate["pgrr_outcome_counts"] == {"PLANNER_FAILURE": 1, "TIMEOUT": 7}
    assert aggregate["base_dynamic_actor_collisions"] == 5
    assert aggregate["base_static_geometry_collisions"] == 1
    assert aggregate["pgrr_recovery_triggered_pairs"] == 7
    assert aggregate["goal_reached_count_both_methods"] == 0
