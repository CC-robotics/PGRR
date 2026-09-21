from pathlib import Path

import h5py
import numpy as np
import pytest

from scripts.student.analyze_dagger_label_mask_distribution import audit_dataset, build_report


def _fixture(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        labels = handle.create_group("labels")
        labels.create_dataset("expert_action", data=[0, 21, 24])
        mask = np.zeros((3, 25), dtype=bool)
        mask[0, [0, 21]] = True
        mask[1, 21] = True
        mask[2, [22, 24]] = True
        labels.create_dataset("action_mask", data=mask)
        labels.create_dataset("expert_margin", data=[0.1, 0.2, 0.3])
        labels.create_dataset("predicted_success", data=[1, 0, 1])
        observations = handle.create_group("observations")
        observations.create_dataset(
            "failure_prediction", data=[[1, 0, 0, 0], [0, 0, 0, 0], [0, 1, 0, 0]]
        )
        observations.create_dataset("episode_start_index", data=[0, 0, 2])
        handle.create_dataset("sample_index", data=[0, 1, 2])


def test_audit_summarizes_labels_masks_and_failure_context(tmp_path: Path):
    path = tmp_path / "fixture.h5"
    _fixture(path)
    report = audit_dataset(path, "fixture", expected_sha256="0" * 64)
    assert report["sample_count"] == 3
    assert report["sha256_matches_expected"] is False
    assert report["episode_count"] == 2
    assert report["action_group_counts"] == {
        "temporary_subgoal": 1,
        "wait": 1,
        "backup": 0,
        "replan": 0,
        "continue": 1,
    }
    assert report["expert_action_permitted_fraction"] == 1.0
    assert report["valid_action_count"] == {
        "minimum": 1,
        "median": 2.0,
        "mean": pytest.approx(5 / 3),
        "maximum": 2,
    }
    assert report["dominant_failure_counts"] == {
        "COLLISION_RISK": 1,
        "FREEZE": 1,
        "NO_POSITIVE_SIGNAL": 1,
    }
    aggregate = build_report([("fixture", path)], {"fixture": "0" * 64})
    assert aggregate["canonical_comparison_ready"] is False
