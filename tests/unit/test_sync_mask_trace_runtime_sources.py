from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/sync_mask_trace_runtime_sources.py"
SPEC = importlib.util.spec_from_file_location("sync_mask_trace_runtime_sources", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path):
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    hashes = {}
    for index, relative in enumerate(sorted(MODULE.ALLOWED_PATHS)):
        source_path = source / relative
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(f"new-{index}\r\n".encode())
        hashes[relative] = MODULE._digest(MODULE._normalized_bytes(source_path))
    existing = runtime / sorted(MODULE.ALLOWED_PATHS)[0]
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("old\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"episode_id": "trace_train", "runtime_source_normalized_sha256": hashes}),
        encoding="utf-8",
    )
    return manifest, source, runtime, existing


def test_syncs_allowlisted_files_with_lf_and_backup(tmp_path: Path) -> None:
    manifest, source, runtime, existing = _fixture(tmp_path)
    relative = existing.relative_to(runtime)
    backup = tmp_path / "backup"

    result = MODULE.sync(manifest, source, runtime, backup)

    assert result["synchronized"]
    assert result["file_count"] == 6
    assert (backup / relative).read_text(encoding="utf-8") == "old\n"
    assert all(b"\r" not in (runtime / item).read_bytes() for item in MODULE.ALLOWED_PATHS)


def test_rejects_existing_backup_or_manifest_outside_allowlist(tmp_path: Path) -> None:
    manifest, source, runtime, _existing = _fixture(tmp_path)
    backup = tmp_path / "backup"
    backup.mkdir()
    with pytest.raises(FileExistsError):
        MODULE.sync(manifest, source, runtime, backup)

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_source_normalized_sha256"]["unexpected.txt"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        MODULE.sync(manifest, source, runtime, tmp_path / "fresh-backup")
