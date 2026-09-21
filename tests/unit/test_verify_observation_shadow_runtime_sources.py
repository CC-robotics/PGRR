import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/verify_observation_shadow_runtime_sources.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_observation_shadow_runtime_sources", SCRIPT
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifest(tmp_path: Path, source: Path) -> Path:
    path = tmp_path / "preflight.json"
    path.write_text(
        json.dumps(
            {
                "episode_id": "shadow_train",
                "runtime_source_normalized_sha256": {
                    "a.py": MODULE._normalized_sha256(source / "a.py"),
                    "nested/b.sh": MODULE._normalized_sha256(source / "nested/b.sh"),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "nested").mkdir(parents=True)
    (root / "a.py").write_text("a\n", encoding="utf-8")
    (root / "nested/b.sh").write_text("b\n", encoding="utf-8")
    return root


def test_accepts_exact_runtime_source_tree(tmp_path: Path) -> None:
    runtime = _source_tree(tmp_path)
    result = MODULE.verify(_manifest(tmp_path, runtime), runtime)

    assert result["ready"]
    assert result["matching_file_count"] == 2
    assert not result["copy_performed"]


def test_reports_stale_and_missing_files_without_copying(tmp_path: Path) -> None:
    runtime = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, runtime)
    (runtime / "a.py").write_text("stale\n", encoding="utf-8")
    (runtime / "nested/b.sh").unlink()

    result = MODULE.verify(manifest, runtime)

    assert not result["ready"]
    assert result["matching_file_count"] == 0
    assert {item["exists"] for item in result["files"]} == {False, True}


def test_treats_crlf_and_lf_as_the_same_runtime_source(tmp_path: Path) -> None:
    runtime = _source_tree(tmp_path)
    manifest = _manifest(tmp_path, runtime)
    (runtime / "a.py").write_bytes(b"a\r\n")
    (runtime / "nested/b.sh").write_bytes(b"b\r\n")

    result = MODULE.verify(manifest, runtime)

    assert result["ready"]
