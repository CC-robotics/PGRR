from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/analyze_mask_constraint_chain.py"
    spec = importlib.util.spec_from_file_location("analyze_mask_chain", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_steps_preserves_order_and_removed_actions() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    reason = (
        "bc_yield_mask=active pre=0,1,21,22 post=0,21,22; "
        "bc_closing_side=right pre=0,21,22 post=21,22; bc_onnx confidence=1.0"
    )

    steps = module.parse_mask_steps(reason)

    assert [step["constraint"] for step in steps] == [
        "bc_yield_mask",
        "bc_closing_side",
    ]
    assert steps[0]["removed"] == (1,)
    assert steps[1]["removed"] == (0,)
    assert module.collapse_source(steps) == "bc_closing_side"


def test_collapse_source_distinguishes_upstream_and_not_collapsed() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])

    upstream = module.parse_mask_steps("bc_yield_mask=active pre=21,22 post=21,22;")
    alternative = module.parse_mask_steps("bc_yield_mask=active pre=0,21 post=0,21;")

    assert module.collapse_source(upstream) == "UPSTREAM_BEFORE_FIRST_LOGGED_STEP"
    assert module.collapse_source(alternative) == "NOT_COLLAPSED_TO_WAIT_BACKUP"
    assert module.collapse_source([]) == "NO_PARSEABLE_MASK_STEP"


def test_parser_accepts_final_and_exposes_unlogged_gap() -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    reason = (
        "bc_closing_side=clear pre=0,3,21,22 post=0,3,21,22; "
        "bc_recurrent_escape=unavailable pre=21,22 final=21,22"
    )

    steps = module.parse_mask_steps(reason)

    assert [step["constraint"] for step in steps] == [
        "bc_closing_side",
        "UNLOGGED_AFTER_bc_closing_side_BEFORE_bc_recurrent_escape",
        "bc_recurrent_escape",
    ]
    assert steps[1]["removed"] == (0, 3)
    assert steps[2]["endpoint_field"] == "final"
    assert module.collapse_source(steps) == (
        "UNLOGGED_AFTER_bc_closing_side_BEFORE_bc_recurrent_escape"
    )
