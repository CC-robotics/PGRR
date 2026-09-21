#!/usr/bin/env python3
"""Create a reproducible, read-only structural snapshot before ROS refactoring."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_NODE = Path("ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py")
OBSERVATION_SEAM = {
    "_observation",
    "_laser_clearance",
    "_observed_laser_clearance",
    "_motion_clearance",
    "_observable_nearest_clearance",
    "_task_path_heading",
    "_task_forward_clearance",
    "_nearest_clearance",
    "_nearest_obstacle_angle",
}
POLICY_SEAM = {
    "_action_mask",
    "_expert_decision",
    "_select_decision",
    "_with_upstream_mask_trace",
}


def _self_calls(method: ast.FunctionDef) -> list[str]:
    names = set()
    for node in ast.walk(method):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "self":
            names.add(node.func.attr)
    return sorted(names)


def _self_attributes(method: ast.FunctionDef) -> list[str]:
    names = set()
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            names.add(node.attr)
    return sorted(names)


def audit_source(path: Path, class_name: str = "RecoveryManagerNode") -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    target = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name),
        None,
    )
    if target is None:
        raise ValueError(f"class not found: {class_name}")
    methods = [node for node in target.body if isinstance(node, ast.FunctionDef)]
    records = []
    method_names = {method.name for method in methods}
    for method in methods:
        calls = _self_calls(method)
        records.append(
            {
                "name": method.name,
                "start_line": method.lineno,
                "end_line": method.end_lineno,
                "line_span": method.end_lineno - method.lineno + 1,
                "internal_method_calls": sorted(set(calls) & method_names),
                "self_attribute_count": len(_self_attributes(method)),
            }
        )

    by_name = {record["name"]: record for record in records}

    def seam(names: set[str]) -> dict[str, Any]:
        present = sorted(names & method_names)
        return {
            "methods": present,
            "method_count": len(present),
            "combined_line_span": sum(by_name[name]["line_span"] for name in present),
            "missing_expected_methods": sorted(names - method_names),
        }

    return {
        "schema_version": 1,
        "source": path.as_posix(),
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "class": class_name,
        "class_start_line": target.lineno,
        "class_end_line": target.end_lineno,
        "class_line_span": target.end_lineno - target.lineno + 1,
        "method_count": len(methods),
        "largest_methods": sorted(
            records, key=lambda item: (-item["line_span"], item["name"])
        )[:10],
        "candidate_seams": {
            "observation_and_geometry": seam(OBSERVATION_SEAM),
            "mask_and_policy_selection": seam(POLICY_SEAM),
        },
        "methods": records,
        "claim_boundary": "static characterization only; no production code moved",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_NODE)
    parser.add_argument("--class-name", default="RecoveryManagerNode")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_source(args.source, args.class_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
