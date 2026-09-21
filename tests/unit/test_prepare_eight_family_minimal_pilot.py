from __future__ import annotations

from scripts.student.prepare_eight_family_minimal_pilot import build_plan


def test_minimal_pair_plan_has_one_base_and_pgrr_attempt_per_family() -> None:
    plan = build_plan()

    assert plan["attempt_count"] == 16
    assert plan["methods"] == ["base", "pgrr"]
    assert [row["order"] for row in plan["rows"]] == list(range(16))
    for family_index in range(8):
        rows = [row for row in plan["rows"] if row["family_index"] == family_index]
        assert [row["method"] for row in rows] == ["base", "pgrr"]
        assert len({row["scenario_sha256"] for row in rows}) == 1
        assert len({row["seed"] for row in rows}) == 1
        assert len({row["ros_domain_id"] for row in rows}) == 2
