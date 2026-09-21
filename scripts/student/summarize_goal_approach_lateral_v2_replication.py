#!/usr/bin/env python3
"""Summarize the predeclared goal-approach v2 train replication gate."""

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
        "seed": 97100,
        "base_stem": "pgrr_priority_goalapproach_v2_train_s97100_base_retry01",
        "pgrr_stem": "pgrr_priority_goalapproach_v2_train_s97100_pgrr",
        "source": "screen",
        "infra_stem": "pgrr_priority_goalapproach_v2_train_s97100_base",
    },
    {
        "replicate": 1,
        "seed": 97101,
        "base_stem": "pgrr_priority_goalapproach_v2_train_r01_s97101_base",
        "pgrr_stem": "pgrr_priority_goalapproach_v2_train_r01_s97101_pgrr",
        "source": "replication",
    },
    {
        "replicate": 2,
        "seed": 97102,
        "base_stem": "pgrr_priority_goalapproach_v2_train_r02_s97102_base",
        "pgrr_stem": "pgrr_priority_goalapproach_v2_train_r02_s97102_pgrr",
        "source": "replication",
    },
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _episode(runtime: Path, stem: str) -> dict[str, Any]:
    outcome_path = runtime / f"{stem}.outcome.json"
    jsonl_path = runtime / f"{stem}.jsonl"
    outcome = _load(outcome_path)
    return {
        "episode_id": outcome["episode_id"],
        "outcome": outcome["outcome"],
        "detail": outcome["detail"],
        "sample_count": int(outcome["sample_count"]),
        "physical_goal_distance_m": (
            float(outcome["physical_goal_distance_m"])
            if "physical_goal_distance_m" in outcome
            else None
        ),
        "scenario_events": outcome.get("scenario_events", []),
        "outcome_path": str(outcome_path),
        "jsonl_path": str(jsonl_path),
    }


def build_summary(screen_runtime: Path, replication_runtime: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    infrastructure_attempts: list[dict[str, Any]] = []
    for run in RUNS:
        runtime = screen_runtime if run["source"] == "screen" else replication_runtime
        base = _episode(runtime, run["base_stem"])
        pgrr = _episode(runtime, run["pgrr_stem"])
        if base["sample_count"] <= 0 or pgrr["sample_count"] <= 0:
            raise ValueError("selected comparison episodes must contain samples")
        recovery = summarize_recovery(Path(pgrr["jsonl_path"]))
        event_chain = [event["transition"] for event in pgrr["scenario_events"]]
        event_complete = event_chain == [
            "pre_event_to_active_event",
            "active_event_to_released",
        ]
        restored = recovery["original_goal_restored_event_count"] >= 1
        positive = base["outcome"] != "GOAL_REACHED" and pgrr["outcome"] == "GOAL_REACHED"
        rows.append(
            {
                "replicate": run["replicate"],
                "seed": run["seed"],
                "base": base,
                "pgrr": pgrr,
                "positive_pair": positive,
                "pgrr_event_chain_complete": event_complete,
                "pgrr_original_goal_restored": restored,
                "pgrr_recovery": {
                    "state_transitions": recovery["state_transitions"],
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
        if "infra_stem" in run:
            infra = _episode(runtime, run["infra_stem"])
            if infra["outcome"] != "SIMULATOR_FAILURE" or infra["sample_count"] != 0:
                raise ValueError("expected preserved zero-sample infrastructure attempt")
            infrastructure_attempts.append(infra)

    qualifying = sum(
        row["positive_pair"]
        and row["pgrr_event_chain_complete"]
        and row["pgrr_original_goal_restored"]
        for row in rows
    )
    return {
        "schema_version": 1,
        "scope": "train_only_replication_gate",
        "family": "goal_approach_lateral_interruption",
        "variant_id": "goal_approach_lateral_one_shot_v2",
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "promotion_rule": {"minimum_qualifying_pairs": 2, "total_pairs": 3},
        "selected_pairs": rows,
        "preserved_infrastructure_attempts": infrastructure_attempts,
        "qualifying_pair_count": qualifying,
        "total_pair_count": len(rows),
        "train_replication_gate_passed": qualifying >= 2,
        "independent_validation_complete": False,
        "paper_claim_authorized": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 目标附近侧向干扰 v2 训练内复现汇总",
        "",
        "| 重复 | seed | Base | PGRR | 事件链 | 原目标恢复 | 合格配对 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for row in summary["selected_pairs"]:
        qualifying = (
            row["positive_pair"]
            and row["pgrr_event_chain_complete"]
            and row["pgrr_original_goal_restored"]
        )
        event_label = "完整" if row["pgrr_event_chain_complete"] else "不完整"
        restored_label = "是" if row["pgrr_original_goal_restored"] else "否"
        qualifying_label = "是" if qualifying else "否"
        lines.append(
            f"| r{row['replicate']:02d} | {row['seed']} | {row['base']['outcome']} | "
            f"{row['pgrr']['outcome']} | {event_label} | {restored_label} | "
            f"{qualifying_label} |"
        )
    lines.extend(
        [
            "",
            f"预声明门槛为至少 2/3 合格配对；实际为 "  # noqa: RUF001
            f"{summary['qualifying_pair_count']}/{summary['total_pair_count']}，"  # noqa: RUF001
            f"训练内复现门槛{'通过' if summary['train_replication_gate_passed'] else '未通过'}。",
            "",
            "这里只完成训练场景复现。尚未执行独立 validation，"  # noqa: RUF001
            "不能据此写成论文中的新场景结论。",
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
