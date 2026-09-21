from pathlib import Path

from scripts.student.build_eight_family_method_metric_matrix import (
    build_matrix,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_matrix_covers_all_families_and_preserves_pair_values() -> None:
    report = build_matrix(
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml",
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml",
        ROOT / "outputs/student/eight_family_pilot/minimal_pair_summary.csv",
    )

    assert len(report["families"]) == 8
    assert {row["family_index"] for row in report["families"]} == set(range(8))
    assert report["comparison_methods"] == ["base", "heuristic", "uniform_bc", "pgrr"]
    lead_stop = next(
        row for row in report["families"] if row["family"] == "lead_pedestrian_sudden_stop"
    )
    assert lead_stop["development_observation"]["base_outcome"] == "COLLISION"
    assert lead_stop["development_observation"]["pgrr_outcome"] == "TIMEOUT"
    assert lead_stop["development_observation"]["pgrr_original_goal_restores"] == 4


def test_every_family_has_outcomes_costs_diagnostics_and_claim_boundary() -> None:
    report = build_matrix(
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml",
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml",
        ROOT / "outputs/student/eight_family_pilot/minimal_pair_summary.csv",
    )

    for row in report["families"]:
        assert row["required_primary_metrics"] == ["GOAL_REACHED", "COLLISION", "TIMEOUT"]
        assert row["required_cost_metrics_on_joint_success"] == [
            "completion_time_s",
            "path_length_m",
            "angular_jerk",
        ]
        assert row["required_mechanism_diagnostics"]
        assert row["mechanism_questions"]
        assert row["development_observation"]["scope"].endswith("descriptive only")
    assert "superiority" in report["claim_boundary"]["forbidden_claims"]


def test_markdown_states_scope_and_does_not_convert_timeouts_to_success() -> None:
    report = build_matrix(
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml",
        ROOT / "configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml",
        ROOT / "outputs/student/eight_family_pilot/minimal_pair_summary.csv",
    )
    markdown = render_markdown(report)

    assert "train-only development evidence" in markdown
    assert "does not establish superiority" in markdown
    assert "Base=COLLISION; PGRR=TIMEOUT" in markdown
    assert "compared only on joint successes" in markdown
