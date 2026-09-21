import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_remaining_families_compile_with_consistent_manifest(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/student"))
    spec = importlib.util.spec_from_file_location(
        "remaining", ROOT / "scripts/student/compile_remaining_family_smokes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = module.compile_all(tmp_path)
    assert len(records) == 2
    for record, count, seed in zip(records, [2, 1], [91610, 91700], strict=True):
        payload = json.loads(Path(record["json"]).read_text())
        assert payload["ramp_metadata"]["seed"] == seed
        assert payload["ramp_metadata"]["split"] == "train"
        assert len(payload["obstacles"]["dynamic"]) == count
        assert Path(record["preview"]).stat().st_size > 0
    assert json.loads((tmp_path / "families_7_8_manifest.json").read_text()) == records
