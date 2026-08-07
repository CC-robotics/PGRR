from __future__ import annotations

import hashlib
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sanitizer = _load_module(
    "sanitize_hdf5_metadata", ROOT / "scripts/bootstrap/sanitize_hdf5_metadata.py"
)


def _private_root() -> str:
    return str(Path.home() / "RAMP")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sanitize_file_changes_only_textual_attributes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "expert.h5"
    expected = np.arange(12, dtype=np.float32).reshape(3, 4)
    with h5py.File(dataset, "w") as handle:
        handle.create_dataset("observations", data=expected)
        handle.attrs["schema_version"] = 1
        handle.attrs["source_jsonl"] = _private_root() + "/data/raw/episode.jsonl"
        handle["observations"].attrs["note"] = '["' + _private_root() + '/data/raw/a.jsonl"]'

    before = _sha256(dataset)
    changes = sanitizer.sanitize_file(dataset, write=False, display_path="expert.h5")
    assert len(changes) == 2
    assert _sha256(dataset) == before

    sanitizer.sanitize_file(dataset, write=True, display_path="expert.h5")
    after = _sha256(dataset)
    assert after != before
    with h5py.File(dataset, "r") as handle:
        np.testing.assert_array_equal(handle["observations"][:], expected)
        assert handle.attrs["schema_version"] == 1
        assert handle.attrs["source_jsonl"] == ("${PROJECT_ROOT}/data/raw/episode.jsonl")
        assert handle["observations"].attrs["note"] == ('["${PROJECT_ROOT}/data/raw/a.jsonl"]')

    assert sanitizer.sanitize_file(dataset, write=True) == []
    assert _sha256(dataset) == after


def test_stale_private_binary_string_forces_clean_repack(tmp_path: Path) -> None:
    dataset = tmp_path / "stale.h5"
    with h5py.File(dataset, "w") as handle:
        handle.create_dataset("values", data=np.arange(4))
        handle.attrs["source_jsonl"] = "data/raw/episode.jsonl"
    with dataset.open("ab") as stream:
        stream.write(("historical=" + _private_root() + "/data/raw/old.jsonl").encode())

    changes = sanitizer.sanitize_file(dataset, write=False, display_path="stale.h5")
    assert changes == [sanitizer.AttributeChange("stale.h5", "<file>", "<stale-metadata>")]
    sanitizer.sanitize_file(dataset, write=True)

    assert _private_root().encode() not in dataset.read_bytes()
    with h5py.File(dataset, "r") as handle:
        np.testing.assert_array_equal(handle["values"][:], np.arange(4))
        assert handle.attrs["source_jsonl"] == "data/raw/episode.jsonl"


def test_tracked_discovery_excludes_untracked_hdf5(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    tracked = tmp_path / "tracked.h5"
    untracked = tmp_path / "untracked.h5"
    for path in (tracked, untracked):
        with h5py.File(path, "w") as handle:
            handle.attrs["source_jsonl"] = "data/raw/episode.jsonl"
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.h5"], check=True)

    assert sanitizer.tracked_hdf5_files(tmp_path) == [tracked]
    assert sanitizer.main(["--root", str(tmp_path), str(untracked), "--write"]) == 2


def test_nested_public_paths_and_alias_identity_are_unchanged() -> None:
    value = "Charles Chen <charles.chen@example.invalid>; ${PROJECT_ROOT}/data/raw/episode.jsonl"
    assert sanitizer.sanitize_text(value) == value
