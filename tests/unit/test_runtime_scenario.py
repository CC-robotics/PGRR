from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_module(root: Path) -> ModuleType:
    module_path = root / "scripts/arena/materialize_runtime_scenario.py"
    spec = importlib.util.spec_from_file_location("materialize_runtime_scenario", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scenario() -> dict[str, object]:
    return {
        "format": "arena-tools",
        "robots": [{"name": "jackal", "start": [1.0, 2.0, 0.0], "goal": [8.0, 2.0, 0.0]}],
        "obstacles": {
            "static": [{"name": "wall", "model": "shelf"}],
            "dynamic": [
                {
                    "name": "pedestrian_0",
                    "model": "gazebo_actor",
                    "pos": [3.0, 2.0, 0.0],
                    "waypoints": [[3.0, 2.0, 0.0], [4.0, 2.0, 0.0]],
                }
            ],
            "custom_field": {"preserve": True},
        },
        "ramp_metadata": {"scenario_id": "unit", "seed": 7, "split": "validation"},
        "unknown_top_level": ["preserved"],
    }


def test_runtime_scenario_removes_only_dynamic_actors_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    source = tmp_path / "source.json"
    output = tmp_path / "default.json"
    original = _scenario()
    source.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    source_bytes = source.read_bytes()

    replace_calls: list[tuple[Path, Path]] = []
    real_replace = module.os.replace

    def recording_replace(temporary: Path, destination: Path) -> None:
        replace_calls.append((Path(temporary), Path(destination)))
        real_replace(temporary, destination)

    monkeypatch.setattr(module.os, "replace", recording_replace)
    module.materialize_runtime_scenario(source, output)

    expected = _scenario()
    expected["obstacles"]["dynamic"] = []  # type: ignore[index]
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert source.read_bytes() == source_bytes
    assert len(replace_calls) == 1
    temporary, destination = replace_calls[0]
    assert temporary.parent == output.parent
    assert temporary != output
    assert destination == output
    assert not temporary.exists()


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"obstacles": []}, {"obstacles": {}}, {"obstacles": {"dynamic": {}}}],
)
def test_runtime_scenario_rejects_invalid_dynamic_actor_schema(
    tmp_path: Path, payload: object
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    source = tmp_path / "invalid.json"
    output = tmp_path / "default.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        module.materialize_runtime_scenario(source, output)

    assert not output.exists()


def test_baseline_runner_sanitizes_task_generator_copy_and_keeps_original_for_controller() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "scripts/arena/run_baseline_episode_inner.sh").read_text(encoding="utf-8")

    assert "materialize_runtime_scenario.py" in runtime
    assert '--source "${SCENARIO}"' in runtime
    assert '--output "${SCENARIO_TARGET}"' in runtime
    assert 'cp "${SCENARIO}" "${SCENARIO_TARGET}"' not in runtime
    assert '-p scenario_file:="${SCENARIO}"' in runtime
