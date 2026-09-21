from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/build_anchor_failure_diagnosis.py"
SPEC = importlib.util.spec_from_file_location("anchor_failure_diagnosis", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PILOT = ROOT / "outputs/student/eight_family_pilot"


def _report() -> dict:
    with (PILOT / "minimal_pair_summary.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        pairs = list(csv.DictReader(stream))
    return MODULE.build_diagnosis(
        pairs,
        json.loads((PILOT / "recovery_progress_diagnostic.json").read_text()),
        json.loads((PILOT / "recovery_control_attribution.json").read_text()),
        json.loads((PILOT / "recovery_contract_probe.json").read_text()),
    )


def test_anchor_counts_match_checked_diagnostics() -> None:
    report = _report()
    aggregate = report["aggregate"]
    assert aggregate["anchor_count"] == 2
    assert aggregate["recovery_cycle_count"] == 6
    assert aggregate["meaningful_progress_cycle_count"] == 0
    assert aggregate["completed_rejoin_count"] == 4


def test_final_masks_identify_candidate_availability_bottleneck() -> None:
    aggregate = _report()["aggregate"]
    assert aggregate["learned_decision_count"] == 15
    assert aggregate["only_wait_backup_allowed_count"] == 13
    assert aggregate["alternative_action_available_count"] == 2


def test_next_gate_does_not_authorize_algorithm_change() -> None:
    report = _report()
    assert report["findings"][0]["name"] == "candidate_availability_bottleneck"
    assert report["next_gate"]["algorithm_change_authorized"] is False
