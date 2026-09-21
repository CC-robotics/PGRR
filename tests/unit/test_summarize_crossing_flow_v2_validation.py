from __future__ import annotations

import json
from pathlib import Path

from scripts.student.summarize_crossing_flow_v2_validation import build_summary


def _write_episode(root: Path, stem: str, outcome: str, samples: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.outcome.json").write_text(
        json.dumps(
            {
                "episode_id": stem,
                "outcome": outcome,
                "detail": "test",
                "sample_count": samples,
                "physical_goal_distance_m": 0.2,
            }
        ),
        encoding="utf-8",
    )
    rows = [
        json.dumps(
            {
                "timestamp": index / 10,
                "recovery_state": 0,
                "recovery_action": 24,
                "recovery_reason": "",
                "goal": [20.0, 12.0],
            }
        )
        for index in range(samples)
    ]
    (root / f"{stem}.jsonl").write_text("\n".join(rows), encoding="utf-8")


def test_validation_summary_promotes_three_positive_pairs_without_retries(
    tmp_path: Path,
) -> None:
    for replicate, seed in enumerate((96000, 96001, 96002)):
        prefix = f"pgrr_advscreen_crossing_v2_validation_r0{replicate}_s{seed}"
        _write_episode(tmp_path, f"{prefix}_base", "COLLISION", 2)
        _write_episode(tmp_path, f"{prefix}_pgrr", "GOAL_REACHED", 3)

    summary = build_summary(tmp_path)

    assert summary["positive_pair_count"] == 3
    assert summary["validation_gate_passed"] is True
    assert summary["validated_new_scenario_count"] == 1
    assert summary["retry_artifacts"] == []
    assert summary["general_superiority_claim_authorized"] is False
    assert summary["frozen_test_used"] is False
