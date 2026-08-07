from __future__ import annotations

from pathlib import Path

import yaml


def test_selected_label_jobs_keep_train_and_validation_outputs_disjoint() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load((root / "data/manifests/selected_label_jobs.yaml").read_text())
    jobs = payload["jobs"]
    outputs = [job["output_hdf5"] for job in jobs]
    assert len(outputs) == len(set(outputs))
    assert {job["split"] for job in jobs} == {"train", "validation"}
    assert all("validation" not in job["raw_jsonl"] for job in jobs if job["split"] == "train")
