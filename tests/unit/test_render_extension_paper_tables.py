from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "student" / "render_extension_paper_tables.py"
    spec = importlib.util.spec_from_file_location("render_extension_paper_tables", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_renderer_writes_protocol_and_variable_tables_without_results(tmp_path: Path) -> None:
    module = _module()
    variables_path, split_path = module.render(CONFIG, tmp_path)

    variables = variables_path.read_text(encoding="utf-8")
    protocol = split_path.read_text(encoding="utf-8")
    assert "diagonal_cut_in_corridor" in variables
    assert "occluded_side_emergence" in variables
    assert "GOAL_REACHED" not in variables
    assert "91000" in protocol
    assert "93000" in protocol
    assert "97000" in protocol
    assert "not materialized" in protocol
