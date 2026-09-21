#!/usr/bin/env python3
"""Validate one diagnostic observation-shadow smoke without judging navigation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SUMMARY_PATTERN = re.compile(r"observation_shadow_summary=(\{[^\r\n]*\})")
FATAL_PATTERNS = {
    "import_error": "ImportError:",
    "parameter_type_error": "InvalidParameterTypeException",
}


def validate_smoke(outcome_path: Path, runtime_log: Path) -> dict[str, Any]:
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    runtime = runtime_log.read_text(encoding="utf-8", errors="replace")
    encoded_summaries = SUMMARY_PATTERN.findall(runtime)
    summaries: list[dict[str, Any]] = []
    decode_errors: list[str] = []
    for encoded in encoded_summaries:
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            decode_errors.append(str(error))
            continue
        if not isinstance(value, dict):
            decode_errors.append("summary is not a JSON object")
            continue
        summaries.append(value)

    summary = summaries[-1] if summaries else {}
    comparison_count = int(summary.get("comparison_count", 0))
    equivalent_count = int(summary.get("equivalent_count", 0))
    mismatch_count = int(summary.get("mismatch_count", -1))
    stored_records = int(summary.get("stored_per_sample_records", -1))
    authority_unchanged = summary.get("authoritative_path_changed") is False
    equality_passed = (
        comparison_count > 0
        and equivalent_count == comparison_count
        and mismatch_count == 0
    )
    bounded_summary = stored_records == 0
    one_decodable_summary = len(encoded_summaries) == 1 and len(summaries) == 1
    fatal_counts = {
        name: runtime.count(pattern) for name, pattern in FATAL_PATTERNS.items()
    }
    fatal_counts["recovery_manager_process_died"] = len(
        re.findall(r"process has died[^\n]*recovery_manager", runtime, re.IGNORECASE)
    )
    runtime_valid = one_decodable_summary and not any(fatal_counts.values())
    valid = runtime_valid and equality_passed and bounded_summary and authority_unchanged

    return {
        "valid": valid,
        "diagnostic_only": True,
        "performance_claim": False,
        "episode_id": outcome.get("episode_id"),
        "outcome": outcome.get("outcome"),
        "outcome_detail": outcome.get("detail"),
        "runtime_valid": runtime_valid,
        "summary_line_count": len(encoded_summaries),
        "decoded_summary_count": len(summaries),
        "summary_decode_errors": decode_errors,
        "comparison_count": comparison_count,
        "equivalent_count": equivalent_count,
        "mismatch_count": mismatch_count,
        "equality_passed": equality_passed,
        "bounded_summary": bounded_summary,
        "authoritative_path_unchanged": authority_unchanged,
        "shadow_summary": summary,
        "fatal_runtime_pattern_counts": fatal_counts,
        "sources": {
            "outcome": str(outcome_path),
            "runtime_log": str(runtime_log),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--runtime-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate_smoke(args.outcome, args.runtime_log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
