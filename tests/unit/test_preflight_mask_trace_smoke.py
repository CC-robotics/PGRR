import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/preflight_mask_trace_smoke.py"
SPEC = importlib.util.spec_from_file_location("preflight_mask_trace_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path, *, split: str = "train") -> Path:
    root = tmp_path / "project"
    scenario = root / "outputs/student/scenario.json"
    scenario.parent.mkdir(parents=True)
    scenario.write_text(
        json.dumps(
            {
                "ramp_metadata": {
                    "scenario_id": "student_trace_smoke",
                    "split": split,
                    "map_id": "map_empty",
                    "seed": 7,
                }
            }
        ),
        encoding="utf-8",
    )
    manager = root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
    action_mask = root / "packages/ramp_core/ramp_core/action_mask.py"
    online = root / "packages/ramp_core/ramp_core/planning/online.py"
    recorder = root / "packages/ramp_core/ramp_core/recovery/mask_trace.py"
    wrapper = root / "scripts/arena/run_baseline_episode.sh"
    runtime = root / "scripts/arena/run_baseline_episode_inner.sh"
    for path in (manager, action_mask, online, recorder, wrapper, runtime):
        path.parent.mkdir(parents=True, exist_ok=True)
    manager.write_text(
        'self.declare_parameter("enable_upstream_mask_trace", False)\n'
        "diagnostics=scan_diagnostics\n"
        'mask_scan_predicates directional_pass=',
        encoding="utf-8",
    )
    action_mask.write_text(
        '"directional_pass": tuple(directional_pass_ids)\n'
        '"capsule_pass": tuple(capsule_pass_ids)',
        encoding="utf-8",
    )
    online.write_text(
        '"category": "initial_overlap_approaching"\n'
        '"minimum_segment_clearance_m"',
        encoding="utf-8",
    )
    wrapper.write_text(
        'mask_trace="${RAMP_ENABLE_UPSTREAM_MASK_TRACE:-0}"', encoding="utf-8"
    )
    runtime.write_text(
        "upstream_mask_trace_ros_value=false\n"
        "upstream_mask_trace_ros_value=true\n"
        '-p enable_upstream_mask_trace:="${upstream_mask_trace_ros_value}"',
        encoding="utf-8",
    )
    recorder.write_text("class MaskTraceRecorder: pass\n", encoding="utf-8")
    return root


def test_preflight_accepts_new_train_only_episode(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    result = MODULE.preflight(root, Path("outputs/student/scenario.json"), "student_new")

    assert result["ready"]
    assert result["split"] == "train"
    assert result["trace_enabled"]
    assert result["diagnostic_only"]
    assert not result["algorithm_change_authorized"]
    assert len(result["runtime_source_normalized_sha256"]) == 6
    assert result["contract_checks"]["original_scan_predicates_traced"]
    assert "RAMP_ENABLE_UPSTREAM_MASK_TRACE=1" in result["command"]


def test_preflight_rejects_non_train_split(tmp_path: Path) -> None:
    root = _fixture(tmp_path, split="test")
    with pytest.raises(ValueError, match="train split"):
        MODULE.preflight(root, Path("outputs/student/scenario.json"), "student_new")


def test_preflight_allows_validation_only_when_explicit(tmp_path: Path) -> None:
    root = _fixture(tmp_path, split="validation")
    result = MODULE.preflight(
        root,
        Path("outputs/student/scenario.json"),
        "student_validation",
        allow_validation=True,
    )

    assert result["ready"]
    assert result["split"] == "validation"
    assert result["allow_validation"]


def test_preflight_refuses_existing_episode(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    existing = root / "data/raw/student_existing.jsonl"
    existing.parent.mkdir(parents=True)
    existing.write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite"):
        MODULE.preflight(root, Path("outputs/student/scenario.json"), "student_existing")
