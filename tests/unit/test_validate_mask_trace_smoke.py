import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/validate_mask_trace_smoke.py"
SPEC = importlib.util.spec_from_file_location("validate_mask_trace_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_fixture(
    tmp_path: Path, reasons: list[str], runtime: str = ""
) -> tuple[Path, Path, Path]:
    jsonl = tmp_path / "episode.jsonl"
    rows = [
        {"timestamp": float(index), "recovery_action": 24, "recovery_reason": reason}
        for index, reason in enumerate(reasons)
    ]
    jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    outcome = tmp_path / "episode.outcome.json"
    outcome.write_text(
        json.dumps({"episode_id": "train_smoke", "outcome": "TIMEOUT", "sample_count": len(rows)}),
        encoding="utf-8",
    )
    log = tmp_path / "runtime.log"
    log.write_text(runtime, encoding="utf-8")
    return jsonl, outcome, log


def test_accepts_complete_ordered_trace_and_shutdown_cleanup(tmp_path: Path) -> None:
    reason = (
        "decision | mask_stage=map_connectivity pre=0,1 post=0,1 removed=- "
        "| mask_stage=observable_scan pre=0,1 post=1 removed=0 "
        "| mask_stage=path_corridor pre=1 post=1 removed=-"
    )
    paths = _write_fixture(
        tmp_path,
        ["normal", reason],
        "Traceback (most recent call last):\nrclpy.executors.ExternalShutdownException\n",
    )
    result = MODULE.validate_smoke(*paths)

    assert result["valid"]
    assert result["trace_decision_row_count"] == 1
    assert result["complete_trace_row_count"] == 1
    assert result["runtime_traceback_count"] == 1
    assert result["temporary_subgoal_layer_totals"]["observable_scan"][
        "temporary_removed_total"
    ] == 1
    assert result["first_temporary_empty_stage_counts"]["none"] == 1


def test_rejects_misordered_or_missing_stage(tmp_path: Path) -> None:
    reason = (
        "mask_stage=observable_scan pre=0 post=0 removed=- | "
        "mask_stage=path_corridor pre=0 post=0 removed=-"
    )
    result = MODULE.validate_smoke(*_write_fixture(tmp_path, [reason]))

    assert not result["valid"]
    assert result["malformed_trace_row_count"] == 1


def test_rejects_known_runtime_failure(tmp_path: Path) -> None:
    reason = " | ".join(f"mask_stage={stage} pre=0 post=0 removed=-" for stage in MODULE.STAGES)
    result = MODULE.validate_smoke(
        *_write_fixture(tmp_path, [reason], "ImportError: cannot import name MaskTraceRecorder")
    )

    assert not result["valid"]
    assert result["fatal_runtime_pattern_counts"]["import_error"] == 1


def test_distinguishes_no_trigger_from_runtime_failure(tmp_path: Path) -> None:
    result = MODULE.validate_smoke(*_write_fixture(tmp_path, ["not_triggered"]))

    assert result["runtime_valid"]
    assert result["trace_status"] == "not_triggered"
    assert not result["valid"]
