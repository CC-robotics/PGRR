import json
from pathlib import Path

import pytest

from scripts.student.preflight_observation_shadow_smoke import preflight


def _fixture(tmp_path: Path, *, split: str = "train") -> Path:
    scenario = tmp_path / "outputs/student/scenario.json"
    scenario.parent.mkdir(parents=True)
    scenario.write_text(
        json.dumps(
            {
                "ramp_metadata": {
                    "scenario_id": "student_shadow",
                    "split": split,
                    "map_id": "map_empty",
                    "seed": 92013,
                }
            }
        ),
        encoding="utf-8",
    )
    manager = tmp_path / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
    wrapper = tmp_path / "scripts/arena/run_baseline_episode.sh"
    runtime = tmp_path / "scripts/arena/run_baseline_episode_inner.sh"
    builder = tmp_path / "packages/ramp_core/ramp_core/recovery/observation_builder.py"
    shadow = tmp_path / "packages/ramp_core/ramp_core/recovery/observation_shadow.py"
    for path in (manager, wrapper, runtime, builder, shadow):
        path.parent.mkdir(parents=True, exist_ok=True)
    manager.write_text(
        'self.declare_parameter("enable_observation_shadow", False)\nreturn reference',
        encoding="utf-8",
    )
    wrapper.write_text(
        'observation_shadow="${RAMP_ENABLE_OBSERVATION_SHADOW:-0}"\n'
        "RAMP_ENABLE_OBSERVATION_SHADOW must be 0 or 1\n"
        "RAMP_ENABLE_OBSERVATION_SHADOW=${observation_shadow}",
        encoding="utf-8",
    )
    runtime.write_text(
        "observation_shadow_ros_value=false\n"
        "observation_shadow_ros_value=true\n"
        '-p enable_observation_shadow:="${observation_shadow_ros_value}"',
        encoding="utf-8",
    )
    builder.write_text("builder\n", encoding="utf-8")
    shadow.write_text("shadow\n", encoding="utf-8")
    return scenario


@pytest.mark.parametrize("split", ["train", "validation"])
def test_preflight_accepts_non_frozen_development_split(tmp_path: Path, split: str) -> None:
    scenario = _fixture(tmp_path, split=split)

    report = preflight(tmp_path, scenario, f"shadow_{split}_fresh")

    assert report["ready"]
    assert report["authoritative_path_changed"] is False
    assert "RAMP_ENABLE_OBSERVATION_SHADOW=1" in report["command"]
    hashes = report["runtime_source_normalized_sha256"]
    assert len(hashes) == 5
    assert all(len(value) == 64 for value in hashes.values())


def test_preflight_rejects_test_split(tmp_path: Path) -> None:
    scenario = _fixture(tmp_path, split="test")

    with pytest.raises(ValueError, match="train or validation"):
        preflight(tmp_path, scenario, "shadow_test")


def test_preflight_rejects_existing_episode(tmp_path: Path) -> None:
    scenario = _fixture(tmp_path)
    raw = tmp_path / "data/raw/shadow_existing.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="overwrite"):
        preflight(tmp_path, scenario, "shadow_existing")
