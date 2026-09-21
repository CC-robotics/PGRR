from __future__ import annotations

import importlib.util
from pathlib import Path

from ramp_core.recovery.progress import RecoveryCycleProgressConfig, RecoveryCycleVerdict


def _load_module(root: Path):
    path = root / "scripts/student/adapt_recovery_cycles_to_progress_contract.py"
    spec = importlib.util.spec_from_file_location("adapt_recovery_cycles", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(
    timestamp: float,
    x: float,
    state: int,
    failure_score: float,
    goal: list[float] | None = None,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "robot_pose": [x, 0.0, 0.0],
        "goal": goal or [10.0, 0.0, 0.0],
        "recovery_state": state,
        "failure_score": failure_score,
    }


def test_adapter_extracts_retrigger_and_censored_cycle() -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    rows = [
        _row(0.0, 0.0, 0, 0.0),
        _row(1.0, 1.0, 2, 0.9),
        _row(2.0, 1.1, 3, 0.2),
        _row(3.0, 1.3, 0, 0.1),
        _row(4.0, 1.4, 0, 0.1),
        _row(5.0, 1.5, 2, 0.9),
        _row(6.0, 1.6, 2, 0.8),
    ]
    config = RecoveryCycleProgressConfig(0.2, 1, 3.0)

    cycles = module.adapt_episode(
        rows,
        config,
        clear_failure_score_threshold=0.35,
        original_goal_tolerance_m=0.01,
    )

    assert len(cycles) == 2
    assert cycles[0]["retrigger_delay_s"] == 2.0
    assert cycles[0]["rapid_retrigger"]
    assert cycles[0]["verdict"] == RecoveryCycleVerdict.RAPID_RETRIGGER.value
    assert cycles[1]["retrigger_delay_s"] is None
    assert not cycles[1]["retrigger_observation_complete"]


def test_adapter_detects_temporary_goal_not_restored() -> None:
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root)
    rows = [
        _row(0.0, 0.0, 0, 0.0),
        _row(1.0, 1.0, 2, 0.8, [2.0, 1.0, 0.0]),
        _row(2.0, 1.5, 0, 0.1, [2.0, 1.0, 0.0]),
        _row(6.0, 2.0, 0, 0.1),
    ]
    config = RecoveryCycleProgressConfig(0.2, 1, 3.0)

    cycle = module.adapt_episode(
        rows,
        config,
        clear_failure_score_threshold=0.35,
        original_goal_tolerance_m=0.01,
    )[0]

    assert cycle["verdict"] == RecoveryCycleVerdict.ORIGINAL_GOAL_NOT_ACTIVE.value
