#!/usr/bin/env python3
"""Audit the static runtime order of PGRR action-mask restrictions."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_CALLS = (
    ("_action_mask", "compute_action_mask", "upstream_unlogged"),
    ("_action_mask", "apply_observable_scan_mask", "upstream_unlogged"),
    ("_action_mask", "apply_path_corridor_mask", "upstream_unlogged"),
    ("_select_decision", "self._action_mask", "upstream_unlogged"),
    ("_select_decision", "constrain_rejoin_actions", "upstream_unlogged"),
    ("_select_decision", "constrain_directional_yield_motion", "logged_pre_post"),
    ("_select_decision", "self._constrain_bc_temporal_closing_side", "logged_pre_post"),
    ("_select_decision", "constrain_near_field_subgoal_radius", "logged_when_changed"),
    ("_select_decision", "constrain_committed_lateral_side", "logged_when_active"),
    ("_select_decision", "constrain_stalled_rejoin", "downstream_unlogged"),
    ("_select_decision", "constrain_stalled_subgoals", "downstream_unlogged"),
    ("_select_decision", "constrain_repeated_replan", "downstream_unlogged"),
    ("_select_decision", "constrain_repeated_backup", "downstream_unlogged"),
    ("_select_decision", "constrain_net_retreat", "downstream_unlogged"),
    ("_select_decision", "constrain_stalled_wait", "downstream_unlogged"),
    ("_select_decision", "self._constrain_bc_recurrent_escape", "logged_pre_final"),
    ("_select_decision", "ensure_safe_wait_fallback", "downstream_unlogged"),
    ("_select_decision", "self._policy.select_action", "inference"),
)


def _call_name(call: ast.Call) -> str:
    parts = []
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _function_calls(tree: ast.AST, function_name: str) -> list[tuple[int, str]]:
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ),
        None,
    )
    if function is None:
        raise ValueError(f"missing runtime function: {function_name}")
    return sorted(
        (node.lineno, _call_name(node)) for node in ast.walk(function) if isinstance(node, ast.Call)
    )


def audit_source(source_path: Path) -> dict[str, Any]:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls_by_scope = {
        scope: _function_calls(tree, scope) for scope in {item[0] for item in EXPECTED_CALLS}
    }
    stages = []
    prior_line_by_scope: dict[str, int] = {}
    for order, (scope, call_name, telemetry) in enumerate(EXPECTED_CALLS, start=1):
        matches = [line for line, name in calls_by_scope[scope] if name == call_name]
        if len(matches) != 1:
            raise ValueError(
                f"expected one {call_name} call in {scope}, observed {len(matches)}"
            )
        line = matches[0]
        if line <= prior_line_by_scope.get(scope, 0):
            raise ValueError(f"unexpected call order at {scope}:{line} ({call_name})")
        prior_line_by_scope[scope] = line
        stages.append(
            {
                "order": order,
                "scope": scope,
                "call": call_name,
                "source_line": line,
                "telemetry": telemetry,
            }
        )

    special_lines = {}
    for label, token in {
        "replan_ready_intersection": "mask[REPLAN_ACTION_ID] &= self._adapter.ready",
        "wait_authorized": "mask[WAIT_ACTION_ID] = True",
        "continue_authorized": "mask[CONTINUE_ACTION_ID] = True",
    }.items():
        if token not in source:
            raise ValueError(f"missing special-action mutation: {token}")
        special_lines[label] = source[: source.index(token)].count("\n") + 1

    return {
        "source": source_path.as_posix(),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "claim_boundary": "static_call_order_not_runtime_causality",
        "stage_count": len(stages),
        "stages": stages,
        "special_action_mutations": special_lines,
        "telemetry_gaps": {
            "upstream_before_yield": [
                "compute_action_mask",
                "apply_observable_scan_mask",
                "apply_path_corridor_mask",
                "special_action_mutations",
                "constrain_rejoin_actions",
            ],
            "between_closing_and_recurrent": [
                "constrain_stalled_rejoin",
                "constrain_stalled_subgoals",
                "constrain_repeated_replan",
                "constrain_repeated_backup",
                "constrain_net_retreat",
                "constrain_stalled_wait",
            ],
            "after_recurrent": ["ensure_safe_wait_fallback"],
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    rows = [
        "# PGRR runtime mask pipeline static audit",
        "",
        f"Source SHA-256: `{report['source_sha256']}`",
        "",
        "| # | Scope | Call | Telemetry coverage | Source line |",
        "|---:|---|---|---|---:|",
    ]
    rows.extend(
        f"| {stage['order']} | `{stage['scope']}` | `{stage['call']}` | "
        f"`{stage['telemetry']}` | {stage['source_line']} |"
        for stage in report["stages"]
    )
    rows.extend(
        [
            "",
            "This artifact verifies static source order only. It does not identify which rule",
            "caused an episode outcome and it does not modify the runtime mask.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_source(args.source)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"stage_count": report["stage_count"]}, indent=2))


if __name__ == "__main__":
    main()
