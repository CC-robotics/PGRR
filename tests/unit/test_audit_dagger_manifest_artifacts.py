import hashlib
import json
from pathlib import Path

from scripts.student.audit_dagger_manifest_artifacts import _local_index, _requirements


def test_manifest_requirements_and_local_hash_index(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    artifact = data / "sample.h5"
    artifact.write_bytes(b"fixture")
    digest = hashlib.sha256(b"fixture").hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset": {"path": "data/sample.h5", "sha256": digest},
                "validation_dataset": {"path": "data/validation.h5", "sha256": "0" * 64},
            }
        ),
        encoding="utf-8",
    )
    requirements = _requirements([manifest])
    assert [item["role"] for item in requirements] == ["dataset", "validation_dataset"]
    assert _local_index(data)[digest] == [artifact.as_posix()]
