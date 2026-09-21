#!/usr/bin/env python3
"""Validate an opt-in upstream-mask telemetry smoke without judging performance."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

STAGES = ("map_connectivity", "observable_scan", "path_corridor")
STAGE_PATTERN = re.compile(r"mask_stage=([a-z_]+)")
TRANSITION_PATTERN = re.compile(
    r"mask_stage=([a-z_]+) pre=([0-9,]+|none) post=([0-9,]+|none)"
)
FATAL_PATTERNS = {
    "import_error": "ImportError:",
    "parameter_type_error": "InvalidParameterTypeException",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        rows.append(value)
    if not rows:
        raise ValueError(f"episode contains no telemetry rows: {path}")
    return rows


def _ids(value: str) -> set[int]:
    return set() if value == "none" else {int(item) for item in value.split(",")}


def validate_smoke(jsonl: Path, outcome_path: Path, runtime_log: Path) -> dict[str, Any]:
    rows = _read_jsonl(jsonl)
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    runtime = runtime_log.read_text(encoding="utf-8", errors="replace")

    traced: list[tuple[int, list[str], str]] = []
    for index, row in enumerate(rows):
        reason = str(row.get("recovery_reason", ""))
        stages = STAGE_PATTERN.findall(reason)
        if stages:
            traced.append((index, stages, reason))

    stage_counts = Counter(stage for _, stages, _ in traced for stage in stages)
    complete_rows = [item for item in traced if tuple(item[1]) == STAGES]
    malformed_rows = [
        {
            "sample_index": index,
            "observed_stages": stages,
            "reason": reason,
        }
        for index, stages, reason in traced
        if tuple(stages) != STAGES
    ]
    action_counts = Counter(str(rows[index].get("recovery_action")) for index, _, _ in traced)
    layer_totals = {
        stage: {
            "temporary_input_total": 0,
            "temporary_output_total": 0,
            "temporary_removed_total": 0,
            "rows_removing_temporary": 0,
            "rows_with_no_temporary_output": 0,
        }
        for stage in STAGES
    }
    first_empty_counts: Counter[str] = Counter()
    for _, _, reason in complete_rows:
        transitions = TRANSITION_PATTERN.findall(reason)
        first_empty = "none"
        for stage, before_text, after_text in transitions:
            before = {item for item in _ids(before_text) if item < 21}
            after = {item for item in _ids(after_text) if item < 21}
            removed = before - after
            totals = layer_totals[stage]
            totals["temporary_input_total"] += len(before)
            totals["temporary_output_total"] += len(after)
            totals["temporary_removed_total"] += len(removed)
            totals["rows_removing_temporary"] += bool(removed)
            totals["rows_with_no_temporary_output"] += not after
            if first_empty == "none" and before and not after:
                first_empty = stage
        first_empty_counts[first_empty] += 1
    fatal_counts = {
        name: runtime.count(pattern) for name, pattern in FATAL_PATTERNS.items()
    }
    fatal_counts["recovery_manager_process_died"] = len(
        re.findall(r"process has died[^\n]*recovery_manager", runtime, re.IGNORECASE)
    )
    expected_shutdown = (
        runtime.count("rclpy.executors.ExternalShutdownException")
        + runtime.count("rcl_shutdown already called on the given context")
    )
    sample_count_matches = int(outcome.get("sample_count", -1)) == len(rows)
    stage_contract_ok = bool(traced) and len(complete_rows) == len(traced)
    fatal_runtime_error = any(fatal_counts.values())
    runtime_valid = sample_count_matches and not fatal_runtime_error
    trace_status = (
        "complete" if stage_contract_ok else "not_triggered" if not traced else "malformed"
    )
    valid = runtime_valid and trace_status == "complete"

    return {
        "valid": valid,
        "runtime_valid": runtime_valid,
        "trace_status": trace_status,
        "diagnostic_only": True,
        "performance_claim": False,
        "episode_id": outcome.get("episode_id"),
        "outcome": outcome.get("outcome"),
        "outcome_detail": outcome.get("detail"),
        "telemetry_row_count": len(rows),
        "outcome_sample_count": outcome.get("sample_count"),
        "sample_count_matches": sample_count_matches,
        "trace_decision_row_count": len(traced),
        "complete_trace_row_count": len(complete_rows),
        "malformed_trace_row_count": len(malformed_rows),
        "stage_counts": {stage: stage_counts[stage] for stage in STAGES},
        "expected_stage_order": list(STAGES),
        "traced_action_counts": dict(sorted(action_counts.items())),
        "temporary_subgoal_layer_totals": layer_totals,
        "first_temporary_empty_stage_counts": {
            name: first_empty_counts[name] for name in (*STAGES, "none")
        },
        "fatal_runtime_pattern_counts": fatal_counts,
        "runtime_traceback_count": runtime.count("Traceback (most recent call last)"),
        "expected_shutdown_exception_count": expected_shutdown,
        "runtime_note": (
            "Tracebacks are shutdown cleanup only"
            if runtime.count("Traceback (most recent call last)") and not fatal_runtime_error
            else "No fatal recovery-manager pattern detected"
        ),
        "malformed_trace_rows": malformed_rows,
        "sources": {
            "jsonl": str(jsonl),
            "outcome": str(outcome_path),
            "runtime_log": str(runtime_log),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--runtime-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate_smoke(args.jsonl, args.outcome, args.runtime_log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
