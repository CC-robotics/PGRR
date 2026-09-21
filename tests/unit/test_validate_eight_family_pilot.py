from __future__ import annotations

from scripts.student.validate_eight_family_pilot import validate


def test_checked_in_eight_family_pilot_is_executable_and_train_only() -> None:
    report = validate()

    assert report["valid"] is True
    assert report["family_count"] == 8
    assert report["verified_scenario_files"] == 8
    assert report["planned_episode_attempts"] == 32
    assert report["held_out_test_materialized"] is False
