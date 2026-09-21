from __future__ import annotations

import json
from pathlib import Path

from scripts.student.summarize_crossing_flow_v2_replication import build_summary


def _write_episode(root: Path, stem: str, outcome: str, samples: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.outcome.json").write_text(
        json.dumps(
            {
                "episode_id": stem,
                "outcome": outcome,
                "detail": "test",
                "sample_count": samples,
                "physical_goal_distance_m": 1.0,
            }
        ),
        encoding="utf-8",
    )
    rows = []
    for index in range(samples):
        rows.append(
            json.dumps(
                {
                    "timestamp": index / 10,
                    "recovery_state": 0,
                    "recovery_action": 24,
                    "recovery_reason": "",
                    "goal": [20.0, 12.0],
                }
            )
        )
    (root / f"{stem}.jsonl").write_text("\n".join(rows), encoding="utf-8")


def test_build_summary_preserves_invalid_retry_and_passes_three_pairs(tmp_path: Path) -> None:
    screen = tmp_path / "screen"
    replication = tmp_path / "replication"
    stems = [
        (screen, "pgrr_advscreen_crossing_v2_train_s95010_base", "COLLISION", 2),
        (screen, "pgrr_advscreen_crossing_v2_train_s95010_pgrr", "GOAL_REACHED", 3),
        (replication, "pgrr_advscreen_crossing_v2_train_r01_s95011_base", "COLLISION", 2),
        (replication, "pgrr_advscreen_crossing_v2_train_r01_s95011_pgrr", "GOAL_REACHED", 3),
        (replication, "pgrr_advscreen_crossing_v2_train_r02_s95012_base", "COLLISION", 2),
        (
            replication,
            "pgrr_advscreen_crossing_v2_train_r02_s95012_pgrr_retry01",
            "GOAL_REACHED",
            3,
        ),
        (
            replication,
            "pgrr_advscreen_crossing_v2_train_r02_s95012_pgrr",
            "INVALID_RESET",
            0,
        ),
    ]
    for args in stems:
        _write_episode(*args)

    summary = build_summary(screen, replication)

    assert summary["positive_pair_count"] == 3
    assert summary["train_replication_gate_passed"] is True
    assert summary["independent_validation_complete"] is False
    assert summary["paper_claim_authorized"] is False
    assert summary["preserved_infrastructure_attempts"][0]["outcome"] == "INVALID_RESET"
