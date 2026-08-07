from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts/arena/render_ros_scalar_parameters.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("render_ros_scalar_parameters", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_preserves_scalar_types_without_shell_evaluation(tmp_path: Path) -> None:
    module = _load_module()
    config = tmp_path / "params.yaml"
    config.write_text(
        "count: 6\nthreshold: 0.2\nenabled: true\nlabel: 'task frame'\n",
        encoding="utf-8",
    )

    assert module.render(config) == [
        "-p",
        "count:=6",
        "-p",
        "threshold:=0.2",
        "-p",
        "enabled:=true",
        "-p",
        'label:="task frame"',
    ]


@pytest.mark.parametrize(
    "payload",
    (
        "nested:\n  value: 1\n",
        "values: [1, 2]\n",
        "empty:\n",
        "'bad name': 1\n",
    ),
)
def test_render_rejects_non_scalar_or_invalid_parameters(tmp_path: Path, payload: str) -> None:
    module = _load_module()
    config = tmp_path / "invalid.yaml"
    config.write_text(payload, encoding="utf-8")

    with pytest.raises((TypeError, ValueError)):
        module.render(config)


def test_canonical_runtime_configs_are_flat_and_renderable() -> None:
    module = _load_module()
    for relative in (
        "configs/failure/rules.yaml",
        "configs/failure/recovery_state_machine.yaml",
    ):
        rendered = module.render(_ROOT / relative)
        assert rendered
        assert len(rendered) % 2 == 0
        assert rendered[::2] == ["-p"] * (len(rendered) // 2)
