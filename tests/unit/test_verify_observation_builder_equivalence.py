import pytest

from scripts.student.verify_observation_builder_equivalence import run_probe


def test_probe_is_exact_for_deterministic_characterization_cases():
    report = run_probe(seed=92001, case_count=32)
    assert report["equivalent"] is True
    assert report["case_count"] == 32
    assert set(case["path_length"] for case in report["cases"]) == {0, 1, 3, 12}
    assert all(value == 0.0 for value in report["field_max_abs_error"].values())
    assert report["shadow_summary"]["comparison_count"] == 32
    assert report["shadow_summary"]["mismatch_count"] == 0
    assert report["shadow_summary"]["stored_per_sample_records"] == 0


def test_probe_rejects_empty_case_set():
    with pytest.raises(ValueError, match="positive"):
        run_probe(seed=92001, case_count=0)
