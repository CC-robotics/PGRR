#!/usr/bin/env python3
"""Summarize the predeclared crossing-flow v2 train replication gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analyze_recovery_trace import summarize_recovery
except ImportError:
    from analyze_recovery_trace import summarize_recovery


RUNS = (
    {
        "replicate": 0,
        "seed": 95010,
        "base_stem": "pgrr_advscreen_crossing_v2_train_s95010_base",
        "pgrr_stem": "pgrr_advscreen_crossing_v2_train_s95010_pgrr",
        "source": "screen",
    },
    {
        "replicate": 1,
        "seed": 95011,
        "base_stem": "pgrr_advscreen_crossing_v2_train_r01_s95011_base",
        "pgrr_stem": "pgrr_advscreen_crossing_v2_train_r01_s95011_pgrr",
        "source": "replication",
    },
    {
        "replicate": 2,
        "seed": 95012,
        "base_stem": "pgrr_advscreen_crossing_v2_train_r02_s95012_base",
        "pgrr_stem": "pgrr_advscreen_crossing_v2_train_r02_s95012_pgrr_retry01",
        "source": "replication",
        "invalid_stem": "pgrr_advscreen_crossing_v2_train_r02_s95012_pgrr",
    },
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _selected_episode(runtime_dir: Path, stem: str) -> dict[str, Any]:
    outcome_path = runtime_dir / f"{stem}.outcome.json"
    jsonl_path = runtime_dir / f"{stem}.jsonl"
    outcome = _load_json(outcome_path)
    return {
        "episode_id": outcome["episode_id"],
        "outcome": outcome["outcome"],
        "detail": outcome["detail"],
        "sample_count": int(outcome["sample_count"]),
        "physical_goal_distance_m": float(outcome["physical_goal_distance_m"]),
        "outcome_path": str(outcome_path),
        "jsonl_path": str(jsonl_path),
    }


def build_summary(screen_runtime: Path, replication_runtime: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    infrastructure_attempts: list[dict[str, Any]] = []
    for specification in RUNS:
        runtime_dir = (
            screen_runtime if specification["source"] == "screen" else replication_runtime
        )
        base = _selected_episode(runtime_dir, specification["base_stem"])
        pgrr = _selected_episode(runtime_dir, specification["pgrr_stem"])
        if base["sample_count"] <= 0 or pgrr["sample_count"] <= 0:
            raise ValueError("selected comparison episodes must contain samples")
        recovery = summarize_recovery(Path(pgrr["jsonl_path"]))
        positive = base["outcome"] != "GOAL_REACHED" and pgrr["outcome"] == "GOAL_REACHED"
        rows.append(
            {
                "replicate": specification["replicate"],
                "seed": specification["seed"],
                "base": base,
                "pgrr": pgrr,
                "positive_pair": positive,
                "pgrr_recovery": {
                    "state_transitions": recovery["state_transitions"],
                    "decision_event_count": recovery["decision_event_count"],
                    "decision_action_counts": recovery["decision_action_counts"],
                    "temporary_subgoal_decision_count": recovery[
                        "temporary_subgoal_decision_count"
                    ],
                    "original_goal_restored_event_count": recovery[
                        "original_goal_restored_event_count"
                    ],
                },
            }
        )
        invalid_stem = specification.get("invalid_stem")
        if invalid_stem:
            invalid = _selected_episode(runtime_dir, invalid_stem)
            if invalid["outcome"] != "INVALID_RESET" or invalid["sample_count"] != 0:
                raise ValueError("expected preserved zero-sample INVALID_RESET before retry")
            infrastructure_attempts.append(invalid)

    positive_count = sum(row["positive_pair"] for row in rows)
    return {
        "schema_version": 1,
        "scope": "train_only_replication_gate",
        "scenario_family": "crossing_flow_medium_anchor_v2",
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "promotion_rule": {"minimum_positive_pairs": 2, "total_pairs": 3},
        "selected_pairs": rows,
        "preserved_infrastructure_attempts": infrastructure_attempts,
        "positive_pair_count": positive_count,
        "total_pair_count": len(rows),
        "train_replication_gate_passed": positive_count >= 2,
        "independent_validation_complete": False,
        "paper_claim_authorized": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Crossing-flow v2 训练内复现汇总",
        "",
        "| 重复 | seed | Base | PGRR | Base样本 | PGRR样本 | 正向配对 |",
        "|---:|---:|---|---|---:|---:|---|",
    ]
    for row in summary["selected_pairs"]:
        lines.append(
            f"| r{row['replicate']:02d} | {row['seed']} | {row['base']['outcome']} | "
            f"{row['pgrr']['outcome']} | {row['base']['sample_count']} | "
            f"{row['pgrr']['sample_count']} | {'是' if row['positive_pair'] else '否'} |"
        )
    lines.extend(
        [
            "",
            f"预声明门槛：至少2/3正向配对；实际 "  # noqa: RUF001
            f"{summary['positive_pair_count']}/{summary['total_pair_count']}，"  # noqa: RUF001
            f"训练内复现门槛{'通过' if summary['train_replication_gate_passed'] else '未通过'}。",
            "",
            "r02 的首次PGRR启动在0样本处发生INVALID_RESET；原始证据已保留，"  # noqa: RUF001
            "同场景、同seed仅重试一次后得到表中有效结果。",
            "",
            "这只证明该场景通过train-only复现门槛。独立validation尚未执行，"  # noqa: RUF001
            "因此不能作为论文中的已验证新场景，也不授权一般优越性结论。",  # noqa: RUF001
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-runtime", type=Path, required=True)
    parser.add_argument("--replication-runtime", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.screen_runtime, args.replication_runtime)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
