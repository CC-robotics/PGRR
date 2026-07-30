from __future__ import annotations

from pathlib import Path

import yaml


def test_baseline_profiles_are_distinct_and_wired_into_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs" / "planner" / "baselines.yaml").read_text())
    profiles = config["profiles"]
    assert profiles["base"]["arena_inter_planner"] == profiles["heuristic"]["arena_inter_planner"]
    assert profiles["base"]["arena_inter_planner"] == profiles["oracle"]["arena_inter_planner"]
    assert profiles["standard"]["arena_inter_planner"] != profiles["base"]["arena_inter_planner"]
    runtime = (root / "scripts" / "arena" / "run_baseline_episode_inner.sh").read_text()
    for profile in profiles.values():
        assert profile["arena_inter_planner"] in runtime
        assert len(profile["behavior_tree_sha256"]) == 64
    assert 'inter_planner:="${INTER_PLANNER}"' in runtime
    assert 'policy_type:="${recovery_policy_type}"' in runtime
    assert '"${SOURCE_POLICY}" == "heuristic" || "${SOURCE_POLICY}" == "oracle"' in runtime


def test_recovery_manager_preserves_task_path_and_continue_restores_goal() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert "if not self._goal_preempted:" in manager
    assert "if action_id in {REPLAN_ACTION_ID, CONTINUE_ACTION_ID}:" in manager
    assert 'elapsed >= self._float("expert_replan_interval_s")' in manager


def test_pending_recovery_is_a_protective_stop() -> None:
    root = Path(__file__).resolve().parents[2]
    mux = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/goal_mux_node.py").read_text()
    assert "pending_stop = self._recovery_state == RecoveryDecision.PENDING_RECOVERY" in mux
    assert "if terminal_stop or pending_stop:" in mux
