import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/summarize_mask_trace_replication.py"
SPEC = importlib.util.spec_from_file_location("summarize_mask_trace_replication", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _report(path: Path, episode_id: str, status: str, traced: int) -> Path:
    payload = {
        "diagnostic_only": True,
        "runtime_valid": True,
        "episode_id": episode_id,
        "outcome": "TIMEOUT",
        "telemetry_row_count": 10,
        "trace_status": status,
        "trace_decision_row_count": traced,
        "first_temporary_empty_stage_counts": {
            "map_connectivity": 0,
            "observable_scan": traced,
            "path_corridor": 0,
            "none": 0,
        },
        "temporary_subgoal_layer_totals": {
            "map_connectivity": {"temporary_removed_total": 0},
            "observable_scan": {"temporary_removed_total": 21 * traced},
            "path_corridor": {"temporary_removed_total": 0},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_summary_keeps_no_trigger_separate_from_complete_trace(tmp_path: Path) -> None:
    train = _report(tmp_path / "train.json", "case_train_r00", "complete", 2)
    validation = _report(
        tmp_path / "validation.json", "case_validation_r00", "not_triggered", 0
    )
    result = MODULE.summarize([train, validation])

    assert result["episode_count"] == 2
    assert result["traced_decision_count"] == 2
    assert result["split_trace_status_counts"]["validation:not_triggered"] == 1
    assert not result["validation_layer_replication_established"]


def test_summary_does_not_claim_validation_failed_when_none_was_supplied(
    tmp_path: Path,
) -> None:
    train = _report(tmp_path / "train.json", "case_train_r00", "complete", 2)
    result = MODULE.summarize([train])

    assert not result["validation_layer_replication_established"]
    assert "no validation report was supplied" in result["claim_boundary"]
