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
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    for profile in profiles.values():
        assert profile["arena_inter_planner"] in runtime
        assert len(profile["behavior_tree_sha256"]) == 64
    assert 'inter_planner:="${INTER_PLANNER}"' in runtime
    assert 'policy_type:="${recovery_policy_type}"' in runtime
    assert '"${SOURCE_POLICY}" == "heuristic" || "${SOURCE_POLICY}" == "bc"' in runtime
    assert "/workspace/.venv-inference/bin/python" in runtime
    assert "-m ramp_ros.nodes.recovery_manager_node" in runtime
    assert 'RAMP_BC_MODEL_PATH="${RAMP_BC_MODEL_PATH:-' in wrapper
    assert "ROS_DOMAIN_ID must be an integer in [0, 232]" in wrapper
    assert "print(len(static_obstacles))" in runtime
    assert 'lidar_static_collision_enabled:="${lidar_static_collision_enabled}"' in runtime
    assert runtime.count('minimum_valid_lidar_range_m:="${minimum_valid_lidar_range_m}"') == 2
    assert "minimum_valid_lidar_range_m=0.34" in runtime
    assert "RAMP_LIDAR_COLLISION_CONFIRMATION_FRAMES:-3" in runtime
    assert 'physical_static_collision_enabled:="${physical_static_collision_enabled}"' in runtime
    assert "static_obstacles_json" in runtime
    assert '"outcome": "SIMULATOR_FAILURE"' in runtime
    assert '"sample_count": 0' in runtime
    assert "collision_omnidirectional_absolute_distance_m=0.70" in runtime
    assert (
        runtime.count(
            'collision_omnidirectional_absolute_distance_m:="${collision_omnidirectional_absolute_distance_m}"'
        )
        == 1
    )
    assert "awk '/\\[RAMP_BASELINE\\] cleanup_started/ {exit} {print}'" in runtime
    assert "maximum_improving_backups=self._integer(" in manager
    assert "self._int(" not in manager


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
    assert "request.entity.name = proxy_name" in actor
    assert "pose update rejected" in actor
    assert "pending is not None and not pending.done()" in actor
    assert "pose update timed out" in actor
    assert "self._pending_target_elapsed" in actor
    assert "Publishing the requested" in actor
    assert "self._actual_proxy_poses" in actor
    assert "self._actual_robot_pose" in actor
    assert "Gazebo actual pedestrian poses are missing or stale" in actor
    assert "/world/default/dynamic_pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V" in runtime
    assert runtime.count("privileged_robot_pose_topic:=/ramp/privileged/robot_pose") == 2
    assert "<static>false</static>" in actor
    assert "<kinematic>false</kinematic>" in actor
    assert "<gravity>false</gravity>" in actor
    assert '<collision name="collision">' not in actor
    assert "self._robot_position = (float(pose.position.x), float(pose.position.y))" in actor
    assert "if self._actual_robot_pose is not None:" in actor
    assert "<static>true</static>" not in actor
    assert "Gazebo rejected a deterministic pedestrian proxy pose update" in logger
    assert "NavigateToPose did not activate within the startup deadline" in logger
    assert "episode start handshake did not complete before the wall-clock deadline" in logger
    assert runtime.count("episode_start_topic:=/ramp/episode_started") == 3
    assert runtime.count("logger_ready_topic:=/ramp/logger_ready") == 2
    assert runtime.count("odometry_is_world_frame:=true") == 3


def test_episode_cleanup_is_bounded_for_every_auxiliary_process() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "scripts/arena/run_baseline_episode_inner.sh").read_text(encoding="utf-8")
    assert "stop_pid_bounded" in runtime
    assert 'stop_pid_bounded "${recovery_node_pid}" INT 10' in runtime
    assert 'stop_pid_bounded "${actor_pid}" INT 10' in runtime
    assert 'kill -KILL "${pid}"' in runtime
    assert 'RAMP_DISABLE_AUTO_RESET:-0}" != "1"' in runtime


def test_episode_logger_rejects_privileged_robot_pose_jumps() -> None:
    root = Path(__file__).resolve().parents[2]
    logger = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py").read_text()
    assert 'declare_parameter("maximum_privileged_pose_jump_m", 1.0)' in logger
    assert "Gazebo robot pose jumped during the active episode" in logger
    assert "math.dist(new_pose[:2], self._privileged_robot_pose[:2])" in logger
    assert 'declare_parameter("physical_goal_tolerance_m", 0.30)' in logger
    assert 'declare_parameter("goal_confirmation_timeout_s", 1.0)' in logger
    assert "localized goal success disagrees with Gazebo robot pose" in logger
    assert logger.count("self._confirm_goal_reached(") == 3
    assert "self._pending_goal_start_wall_s" in logger


def test_recovery_safety_has_omnidirectional_footprint_guard() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert manager.count("footprint_stop_clearance_m") >= 3
    assert manager.count("_footprint_stop_distance(") >= 3
    config = yaml.safe_load((root / "configs/failure/recovery_state_machine.yaml").read_text())
    assert config["footprint_stop_clearance_m"] == 0.48
    assert config["collision_latched_stop_clearance_m"] == 0.85
    assert config["collision_latched_action_clearance_m"] == 0.65
    assert config["maximum_recovery_path_deviation_m"] == 0.9
    assert config["emergency_rotation_clearance_m"] == 0.24
    assert config["emergency_forward_entry_clearance_m"] == 0.85
    assert config["emergency_backup_reset_clear_s"] == 3.0
    assert config["emergency_maximum_improving_backups"] == 8
    assert config["emergency_backup_progress_m"] == 0.05
    assert config["emergency_translation_clearance_m"] == 0.36
    assert config["bc_wait_budget_decisions"] == 3
    assert config["bc_replan_budget_decisions"] == 1
    assert config["bc_rejoin_block_threshold"] == 0.65
    assert '"emergency_rotation_clearance_m": 0.24' in manager
    assert '"emergency_backup_reset_clear_s": 3.0' in manager
    assert "apply_observable_scan_mask(" in manager
    assert manager.count("_forward_escape_clearance()") >= 2
    assert 'translation_clearance = self._float("emergency_translation_clearance_m")' in manager
    assert 'self._float("collision_latched_stop_clearance_m")' in manager
    detector = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/failure_detector_node.py").read_text()
    assert "RecoveryDecision.EMERGENCY_STOP" in detector
    assert "timestamp <= self._last_timestamp" in detector
    assert "self._detector.reset()" not in detector


def test_oracle_rejoin_distinguishes_hard_risk_from_soft_latch() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert '"expert_rejoin_block_threshold": 0.9' in manager
    assert 'release_threshold=self._float("expert_rejoin_block_threshold")' in manager
    assert 'release_threshold=self._float("bc_rejoin_block_threshold")' in manager
