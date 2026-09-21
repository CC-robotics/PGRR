from __future__ import annotations

import json
from pathlib import Path

from scripts.student.collect_eight_family_pilot_results import collect


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_successful_attempt(data_root: Path, episode_id: str, outcome: str) -> None:
    _write_json(
        data_root / f"{episode_id}.outcome.json",
        {
            "detail": "test",
            "outcome": outcome,
            "sample_count": 1,
            "physical_goal_distance_m": 1.0,
            "localized_goal_distance_m": 1.0,
        },
    )
    _write_json(data_root / f"{episode_id}.metadata.json", {"episode_id": episode_id})
    _write_json(
        data_root / f"{episode_id}.jsonl",
        {
            "timestamp": 0.0,
            "goal": [1.0, 1.0],
            "recovery_state": 0,
            "recovery_action": 24,
            "recovery_reason": "not_triggered",
        },
    )


def test_collector_preserves_infrastructure_attempt_and_selects_valid_retry(tmp_path: Path) -> None:
    plan = tmp_path / "plan.tsv"
    plan.write_text(
        "family_index\tfamily\tmethod\tepisode_id\tscenario_id\tscenario_sha256\tseed\n"
        "2\trecurrent\tbase\tepisode_base\tscenario\thash\t91210\n"
        "2\trecurrent\tpgrr\tepisode_pgrr\tscenario\thash\t91210\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / "episode_base.outcome.json",
        {
            "detail": "startup failed",
            "outcome": "SIMULATOR_FAILURE",
            "sample_count": 0,
        },
    )
    _write_successful_attempt(tmp_path, "episode_base_retry01", "TIMEOUT")
    _write_successful_attempt(tmp_path, "episode_pgrr", "TIMEOUT")

    report = collect(plan, tmp_path)

    assert report["complete_pair_count"] == 1
    base = report["pairs"][0]["runs"]["base"]
    assert base["selected_attempt_id"] == "episode_base_retry01"
    assert [attempt["outcome"] for attempt in base["attempt_history"]] == [
        "SIMULATOR_FAILURE",
        "TIMEOUT",
    ]
