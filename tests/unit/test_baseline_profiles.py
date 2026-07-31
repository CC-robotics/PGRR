from __future__ import annotations

from pathlib import Path

import yaml


def test_baseline_profiles_are_distinct_and_wired_into_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs" / "planner" / "baselines.yaml").read_text())
    profiles = config["profiles"]
    assert profiles["base"]["arena_inter_planner"] == profiles["heuristic"]["arena_inter_planner"]
    assert profiles["base"]["arena_inter_planner"] == profiles["bc"]["arena_inter_planner"]
    assert profiles["base"]["arena_inter_planner"] == profiles["oracle"]["arena_inter_planner"]
    assert profiles["standard"]["arena_inter_planner"] != profiles["base"]["arena_inter_planner"]
    runtime = (root / "scripts" / "arena" / "run_baseline_episode_inner.sh").read_text()
    wrapper = (root / "scripts" / "arena" / "run_baseline_episode.sh").read_text()
    for profile in profiles.values():
        assert profile["arena_inter_planner"] in runtime
        assert len(profile["behavior_tree_sha256"]) == 64
    assert 'inter_planner:="${INTER_PLANNER}"' in runtime
    assert 'policy_type:="${recovery_policy_type}"' in runtime
    assert '"${SOURCE_POLICY}" == "heuristic" || "${SOURCE_POLICY}" == "bc"' in runtime
    assert "/workspace/.venv-inference/bin/python" in runtime
    assert "-m ramp_ros.nodes.recovery_manager_node" in runtime
    assert 'RAMP_BC_MODEL_PATH="${RAMP_BC_MODEL_PATH:-' in wrapper


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
    assert "if not self._episode_started or terminal_stop or pending_stop:" in mux


def test_collision_sector_covers_turning_sweep_without_side_wall() -> None:
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs/failure/rules.yaml").read_text())
    assert config["collision_front_sector_degrees"] == 30.0
    assert config["collision_trend_sector_degrees"] == 90.0
    assert config["collision_trend_sector_degrees"] < 180.0


def test_runtime_uses_configured_ttc_horizon_without_legacy_override() -> None:
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs/failure/rules.yaml").read_text())
    runtime = (root / "scripts" / "arena" / "run_baseline_episode_inner.sh").read_text()
    wrapper = (root / "scripts" / "arena" / "run_baseline_episode.sh").read_text()
    assert config["ttc_threshold_s"] == 1.5
    assert 'TTC_THRESHOLD_S="${RAMP_TTC_THRESHOLD_S:-1.5}"' in runtime
    assert '-p ttc_threshold_s:="${TTC_THRESHOLD_S}"' in runtime
    assert 'RAMP_TTC_THRESHOLD_S="${RAMP_TTC_THRESHOLD_S:-1.5}"' in wrapper
    assert "-p ttc_threshold_s:=3.0" not in runtime


def test_runtime_synchronizes_actor_and_logger_to_navigation_activation() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "scripts" / "arena" / "run_baseline_episode_inner.sh").read_text()
    actor = (
        root / "ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py"
    ).read_text()
    logger = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py").read_text()
    assert runtime.count("-p wait_for_navigation_active:=true") == 2
    assert '-p nav_status_topic:="${nav_action}/_action/status"' in runtime
    assert "-p navigation_activation_timeout_s:=20.0" in runtime
    assert "if self._experiment_started else 0.0" in actor
    assert "released actor routes" in actor
    assert "episode handshake complete" in actor
    assert "and self._logger_ready" in actor
    assert "self._ready_publisher.publish(ready)" in logger
    assert "entity_names = (proxy_name,)" in actor
    assert "pose update rejected" in actor
    assert "Gazebo rejected a deterministic pedestrian proxy pose update" in logger
    assert "NavigateToPose did not activate within the startup deadline" in logger
    assert "episode start handshake did not complete before the wall-clock deadline" in logger
    assert runtime.count("episode_start_topic:=/ramp/episode_started") == 3
    assert runtime.count("logger_ready_topic:=/ramp/logger_ready") == 2


def test_recovery_safety_has_omnidirectional_footprint_guard() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert manager.count("footprint_stop_clearance_m") >= 3
    assert manager.count("_footprint_stop_distance(") >= 3
    config = yaml.safe_load((root / "configs/failure/recovery_state_machine.yaml").read_text())
    assert config["footprint_stop_clearance_m"] == 0.48
    assert config["collision_latched_stop_clearance_m"] == 0.55
    assert config["emergency_rotation_clearance_m"] == 0.24
    assert config["emergency_backup_reset_clear_s"] == 3.0
    assert config["bc_wait_budget_decisions"] == 3
    assert config["bc_replan_budget_decisions"] == 1
    assert config["bc_rejoin_block_threshold"] == 0.65
    assert '"emergency_rotation_clearance_m": 0.24' in manager
    assert '"emergency_backup_reset_clear_s": 3.0' in manager
    assert "apply_observable_scan_mask(" in manager
    detector = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/failure_detector_node.py").read_text()
    assert "RecoveryDecision.EMERGENCY_STOP" in detector


def test_oracle_rejoin_distinguishes_hard_risk_from_soft_latch() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert '"expert_rejoin_block_threshold": 0.9' in manager
    assert 'release_threshold=self._float("expert_rejoin_block_threshold")' in manager
    assert 'release_threshold=self._float("bc_rejoin_block_threshold")' in manager
