from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():  # type: ignore[no-untyped-def]
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "data" / "convert_raw_episode.py"
    spec = importlib.util.spec_from_file_location("convert_raw_episode", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deduplicate_steps_removes_equal_stamps_only() -> None:
    module = _module()

    class Step:
        def __init__(self, timestamp: float) -> None:
            self.timestamp = timestamp

    steps, removed = module._deduplicate_steps([Step(0.0), Step(0.0), Step(0.1)])
    assert [step.timestamp for step in steps] == [0.0, 0.1]
    assert removed == 1


def test_deduplicate_steps_rejects_backwards_time() -> None:
    module = _module()

    class Step:
        def __init__(self, timestamp: float) -> None:
            self.timestamp = timestamp

    try:
        module._deduplicate_steps([Step(0.1), Step(0.0)])
    except ValueError as error:
        assert "backwards" in str(error)
    else:
        raise AssertionError("backwards timestamps must be rejected")
