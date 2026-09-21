#!/usr/bin/env python3
"""Build a checked-source claim ledger for the extension development evidence."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "outputs/student/eight_family_pilot"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_ledger(source_root: Path) -> dict[str, Any]:
    pair_path = source_root / "minimal_pair_summary.csv"
    contract_path = source_root / "recovery_contract_probe.json"
    mask_path = source_root / "mask_trace_replication_summary.json"
    trigger_path = source_root / "trigger_coverage_audit_20260912.json"
    preflight_path = source_root / "mask_trace_leadstop_validation_preflight.json"
    runtime_path = source_root / "mask_trace_leadstop_validation_runtime_validation.json"
    timeout_path = source_root / "leadstop_validation_timeout_diagnosis.json"
    required = (
        pair_path,
        contract_path,
        mask_path,
        trigger_path,
        preflight_path,
        runtime_path,
        timeout_path,
    )
    missing = [path.as_posix() for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing ledger sources: {missing}")

    with pair_path.open(encoding="utf-8", newline="") as stream:
        pairs = list(csv.DictReader(stream))
    contract = _json(contract_path)
    mask = _json(mask_path)
    trigger = _json(trigger_path)
    preflight = _json(preflight_path)
    runtime = _json(runtime_path)
    timeout = _json(timeout_path)

    base_outcomes = Counter(row["base_outcome"] for row in pairs)
    pgrr_outcomes = Counter(row["pgrr_outcome"] for row in pairs)
    if any(row["pgrr_outcome"] == "GOAL_REACHED" for row in pairs):
        raise ValueError("ledger assumptions changed: development PGRR goal reach exists")
    if mask.get("performance_claim") is not False:
        raise ValueError("mask report must remain diagnostic-only")
    if preflight.get("ready") is not True or preflight.get("split") != "validation":
        raise ValueError("selected validation candidate is not preflight-ready")
    if runtime.get("valid") is not True or runtime.get("diagnostic_only") is not True:
        raise ValueError("validation runtime evidence is not valid diagnostic output")
    if timeout.get("causal_claim") is not False or timeout.get("outcome") != "TIMEOUT":
        raise ValueError("validation timeout evidence exceeds its diagnostic boundary")

    return {
        "schema_version": 1,
        "scope": "extension development evidence only",
        "paper_number_policy": "all numbers below are generated from listed checked-in CSV/JSON",
        "claims": [
            {
                "id": "development_pair_outcomes",
                "allowed_statement": (
                    "In eight train-only development pairs, Base collided in six; "
                    "PGRR collided in none but also reached no goals."
                ),
                "numbers": {
                    "pair_count": len(pairs),
                    "base_outcomes": dict(sorted(base_outcomes.items())),
                    "pgrr_outcomes": dict(sorted(pgrr_outcomes.items())),
                },
                "source": _display(pair_path),
                "forbidden_inference": "superiority, generalization, or statistical significance",
            },
            {
                "id": "recovery_cycle_contract_probe",
                "allowed_statement": (
                    "The explicit train-only progress contract found task progress in "
                    "zero of 30 recovery cycles; this diagnoses the prototype, not causality."
                ),
                "numbers": contract["aggregate"],
                "source": _display(contract_path),
                "forbidden_inference": "runtime threshold choice or causal attribution",
            },
            {
                "id": "upstream_mask_trace",
                "allowed_statement": (
                    "Across three selector-positive development episodes, including one "
                    "validation episode, 350 decisions had complete layer traces; this "
                    "establishes selector-layer replication across splits for the diagnostic "
                    "path, not navigation success."
                ),
                "numbers": {
                    "episode_count": mask["episode_count"],
                    "traced_decision_count": mask["traced_decision_count"],
                    "first_temporary_empty_stage_counts": mask[
                        "first_temporary_empty_stage_counts"
                    ],
                    "validation_layer_replication_established": mask[
                        "validation_layer_replication_established"
                    ],
                },
                "source": _display(mask_path),
                "forbidden_inference": "mask causality, performance benefit, or threshold tuning",
            },
            {
                "id": "validation_trigger_paths",
                "allowed_statement": (
                    "The audited validation samples include a detector-negative diagonal case "
                    "and an emergency-only head-on case; neither supplies a selector-layer trace."
                ),
                "numbers": {"diagnosis_counts": trigger["diagnosis_counts"]},
                "source": _display(trigger_path),
                "forbidden_inference": "all validation episodes stayed NORMAL or detector failure",
            },
            {
                "id": "next_validation_candidate",
                "allowed_statement": (
                    "The preflighted non-frozen lead-stop validation episode ran to a preserved "
                    "TIMEOUT and produced 191 complete selector-layer traces."
                ),
                "numbers": {
                    "ready": preflight["ready"],
                    "seed": preflight["seed"],
                    "timeout_s": preflight["timeout_s"],
                    "outcome": runtime["outcome"],
                    "telemetry_row_count": runtime["telemetry_row_count"],
                    "complete_trace_row_count": runtime["complete_trace_row_count"],
                },
                "source": _display(runtime_path),
                "forbidden_inference": (
                    "navigation success, performance superiority, or held-out test result"
                ),
            },
            {
                "id": "validation_timeout_diagnostic",
                "allowed_statement": (
                    "In one non-frozen validation development episode, "
                    f"{timeout['cycle_summary']['nonpositive_progress_cycle_count']} of "
                    f"{timeout['cycle_summary']['cycle_count']} recovery cycles ended no "
                    "closer to the original goal; "
                    f"{timeout['trace_constraint_summary']['directional_yield_active_row_count']} "
                    "selector rows used the directional-yield WAIT/BACKUP restriction."
                ),
                "numbers": {
                    "cycle_summary": timeout["cycle_summary"],
                    "goal_distance": timeout["goal_distance"],
                    "path_length": timeout["path_length"],
                    "trace_constraint_summary": timeout["trace_constraint_summary"],
                },
                "source": _display(timeout_path),
                "forbidden_inference": (
                    "that BACKUP, directional yield, or any mask caused the TIMEOUT"
                ),
            },
        ],
        "global_forbidden_claims": [
            "The eight-family extension establishes PGRR superiority.",
            "The mask trace proves the action mask causes failure.",
            "The validation TIMEOUT is a navigation success.",
            "Directional yield or BACKUP is proven to cause the validation TIMEOUT.",
            "Development train/validation evidence is a held-out test result.",
        ],
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Extension evidence-to-claim ledger",
        "",
        "> Generated from checked-in development CSV/JSON; not a held-out result.",
        "",
    ]
    for claim in ledger["claims"]:
        lines.extend(
            [
                f"## {claim['id']}",
                "",
                f"- Allowed: {claim['allowed_statement']}",
                f"- Forbidden inference: {claim['forbidden_inference']}",
                f"- Source: `{claim['source']}`",
                f"- Generated numbers: `{json.dumps(claim['numbers'], sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(["## Globally forbidden claims", ""])
    lines.extend(f"- {value}" for value in ledger["global_forbidden_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    ledger = build_ledger(args.source_root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(ledger), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
