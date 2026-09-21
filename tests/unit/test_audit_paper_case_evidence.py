from __future__ import annotations

import hashlib

from scripts.student.audit_paper_case_evidence import verified


def test_verified_requires_matching_hash(tmp_path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("evidence", encoding="utf-8")
    expected = hashlib.sha256(b"evidence").hexdigest()
    assert verified(artifact, expected)
    assert not verified(artifact, "0" * 64)


def test_verified_rejects_missing_file(tmp_path) -> None:
    assert not verified(tmp_path / "missing", "0" * 64)
