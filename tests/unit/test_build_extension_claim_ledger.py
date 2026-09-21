import json
from pathlib import Path

from scripts.student.build_extension_claim_ledger import build_ledger, render_markdown


def test_build_ledger_from_checked_in_development_sources() -> None:
    root = Path(__file__).resolve().parents[2] / "outputs/student/eight_family_pilot"
    ledger = build_ledger(root)
    claims = {item["id"]: item for item in ledger["claims"]}
    pair = claims["development_pair_outcomes"]["numbers"]
    assert pair["pair_count"] == 8
    assert pair["base_outcomes"] == {"COLLISION": 6, "TIMEOUT": 2}
    assert pair["pgrr_outcomes"] == {"PLANNER_FAILURE": 1, "TIMEOUT": 7}
    assert claims["upstream_mask_trace"]["numbers"]["traced_decision_count"] == 350
    assert (
        claims["upstream_mask_trace"]["numbers"]["validation_layer_replication_established"] is True
    )
    assert claims["next_validation_candidate"]["numbers"]["ready"] is True
    assert claims["next_validation_candidate"]["numbers"]["outcome"] == "TIMEOUT"
    assert claims["next_validation_candidate"]["numbers"]["complete_trace_row_count"] == 191
    timeout = claims["validation_timeout_diagnostic"]["numbers"]
    assert timeout["cycle_summary"]["cycle_count"] == 4
    assert timeout["cycle_summary"]["positive_progress_cycle_count"] == 0
    assert timeout["trace_constraint_summary"]["temporary_subgoal_selected_count"] == 0
    assert "not a held-out result" in render_markdown(ledger)


def test_ledger_rejects_unready_preflight(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "outputs/student/eight_family_pilot"
    for name in (
        "minimal_pair_summary.csv",
        "recovery_contract_probe.json",
        "mask_trace_replication_summary.json",
        "trigger_coverage_audit_20260912.json",
        "mask_trace_leadstop_validation_preflight.json",
        "mask_trace_leadstop_validation_runtime_validation.json",
        "leadstop_validation_timeout_diagnosis.json",
    ):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    path = tmp_path / "mask_trace_leadstop_validation_preflight.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["ready"] = False
    path.write_text(json.dumps(value), encoding="utf-8")
    try:
        build_ledger(tmp_path)
    except ValueError as error:
        assert "not preflight-ready" in str(error)
    else:
        raise AssertionError("unready preflight must be rejected")
