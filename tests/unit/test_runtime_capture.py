from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "arena" / "record_runtime_capture.py"
SPEC = importlib.util.spec_from_file_location("record_runtime_capture", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_record_capture_uses_relative_privacy_safe_provenance(tmp_path: Path) -> None:
    root = tmp_path / "public"
    screenshot = root / "outputs/figures/runtime/live.png"
    screenshot.parent.mkdir(parents=True)
    Image.new("RGB", (800, 600), color=(24, 90, 140)).save(screenshot)
    scenario = root / "scenarios/example.json"
    _write_json(
        scenario,
        {
            "ramp_metadata": {
                "scenario_id": "doorway_medium_r0",
                "family": "doorway_bottleneck",
                "density": "medium",
                "seed": 73,
                "split": "validation",
            }
        },
    )
    episode_id = "runtime_capture_example"
    outcome = root / f"data/raw/{episode_id}.outcome.json"
    _write_json(outcome, {"episode_id": episode_id, "outcome": "GOAL_REACHED"})
    window_info = root / "outputs/figures/runtime/live.window.json"
    _write_json(
        window_info,
        {
            "capture_backend": "PyQt5.QScreen.grabWindow(X11 window)",
            "capture_context": {
                "framing": "scenario_midpoint_oblique",
                "transport_service": "/gui/move_to/pose",
            },
            "selected_window": {
                "title": "Gazebo",
                "width": 800,
                "height": 600,
            },
            "visual_validation": {
                "grayscale_stddev": 25.0,
                "scene_viewport_grayscale_stddev": 30.0,
                "scene_viewport_unique_colors": 500,
            },
        },
    )
    runtime_log = root / "outputs/logs/capture/runtime.log"
    capture_log = root / "outputs/logs/capture/capture.log"
    runtime_log.parent.mkdir(parents=True)
    runtime_log.write_text("runtime", encoding="utf-8")
    capture_log.write_text("capture", encoding="utf-8")
    metadata_output = root / "outputs/figures/runtime/live.metadata.json"
    paper_copy = root / "paper/figures/runtime_live.png"

    payload = MODULE.record_capture(
        root=root,
        screenshot=screenshot,
        paper_copy=paper_copy,
        metadata_output=metadata_output,
        window_info=window_info,
        scenario=scenario,
        outcome=outcome,
        runtime_log=runtime_log,
        capture_log=capture_log,
        git_commit="a" * 40,
        arena_image_id="sha256:" + "b" * 64,
        ros_domain_id=226,
        gazebo_partition="pgrr_capture",
        episode_id=episode_id,
        captured_at="2026-08-05T00:00:00Z",
    )

    encoded = json.dumps(payload)
    assert str(tmp_path) not in encoded
    assert payload["artifact_type"] == "real_arena_gazebo_gui_screenshot"
    assert payload["scenario"]["path"] == "scenarios/example.json"
    assert payload["artifacts"]["screenshot"] == "outputs/figures/runtime/live.png"
    assert paper_copy.read_bytes() == screenshot.read_bytes()


def test_record_capture_rejects_png_text_metadata(tmp_path: Path) -> None:
    screenshot = tmp_path / "leaky.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Source", "/private/home/project")
    Image.new("RGB", (800, 600), color=(20, 30, 40)).save(screenshot, pnginfo=metadata)
    try:
        MODULE._validate_clean_png(screenshot)
    except ValueError as error:
        assert "ancillary metadata" in str(error)
    else:
        raise AssertionError("PNG text metadata was accepted")


def test_capture_wrapper_is_isolated_and_never_uses_headless_two() -> None:
    wrapper = (ROOT / "scripts/arena/capture_gazebo_snapshot.sh").read_text()
    inner = (ROOT / "scripts/arena/capture_gazebo_snapshot_inner.sh").read_text()
    shim = (ROOT / "scripts/arena/capture_shims/xvfb-run").read_text()
    assert 'RAMP_CAPTURE_ARENA_HEADLESS="0"' in wrapper
    assert 'ROS_DOMAIN_ID="${ros_domain_id}"' in wrapper
    assert 'GZ_PARTITION="${gazebo_partition}"' in wrapper
    assert "Xvfb" in inner
    assert "capture_x11_window.py" in inner
    assert "worlds/.generated/scenarios" in inner
    assert "/gui/move_to/pose" in inner
    assert "ignition.msgs.GUICamera" in inner
    assert (
        "scene_viewport_grayscale_stddev"
        in (ROOT / "scripts/arena/capture_x11_window.py").read_text()
    )
    assert 'command[index]="headless:=${RAMP_CAPTURE_ARENA_HEADLESS:-0}"' in shim


def test_capture_only_xvfb_shim_enables_real_gui() -> None:
    shim = ROOT / "scripts/arena/capture_shims/xvfb-run"
    environment = os.environ.copy()
    environment.update({"DISPLAY": ":199", "RAMP_CAPTURE_ARENA_HEADLESS": "0"})
    result = subprocess.run(
        [
            str(shim),
            "-a",
            "-s",
            "-screen 0 1280x720x24",
            "/usr/bin/printf",
            "%s\\n",
            "ros2",
            "launch",
            "arena_bringup",
            "headless:=2",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.stdout.splitlines()[-1] == "headless:=0"


def test_capture_wrapper_rejects_a_test_scenario_before_launch(tmp_path: Path) -> None:
    scenario = tmp_path / "scenarios/test.json"
    _write_json(scenario, {"ramp_metadata": {"split": "test"}})
    environment = os.environ.copy()
    environment["PROJECT_ROOT"] = str(tmp_path)

    result = subprocess.run(
        [str(ROOT / "scripts/arena/capture_gazebo_snapshot.sh"), str(scenario)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert "requires a validation scenario" in result.stderr
