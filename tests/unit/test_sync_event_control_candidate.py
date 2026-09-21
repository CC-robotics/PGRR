from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/sync_event_control_candidate.py"


def _module():
    spec = importlib.util.spec_from_file_location("sync_event_candidate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_is_allowlisted_backed_up_and_lf_normalized(tmp_path: Path) -> None:
    module = _module()
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    backup = tmp_path / "backup"
    for index, (relative, mode) in enumerate(module.ALLOWED_PATHS.items()):
        source_path = source / relative
        target_path = runtime / relative
        source_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(f"new-{index}\r\n".encode())
        target_path.write_text(f"old-{index}\n", encoding="utf-8")
        target_path.chmod(mode)
    result = module.sync(source, runtime, backup)
    assert result["synchronized"] is True
    assert result["file_count"] == len(module.ALLOWED_PATHS)
    for index, relative in enumerate(module.ALLOWED_PATHS):
        assert (runtime / relative).read_bytes() == f"new-{index}\n".encode()
        assert (backup / relative).read_text(encoding="utf-8") == f"old-{index}\n"
