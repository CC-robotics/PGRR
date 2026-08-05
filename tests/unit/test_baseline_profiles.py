from __future__ import annotations

from pathlib import Path

import pytest
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
    assert (
        'model_path="${RAMP_BC_MODEL_PATH:-/workspace/checkpoints/bc/'
        'uniform_scenario/best.onnx}"' in runtime
    )
    assert '-p model_path:="${model_path}"' in runtime
    assert 'model_path:="${model_path:-}"' not in runtime
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
    assert '[[ -s "${outcome_file}" ]] && return 0' in runtime
    assert 'record_startup_failure "${missing_artifact_detail}"' in runtime
    assert "episode logger exited without complete artifacts (status=${logger_status})" in runtime
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
    assert config["collision_proximity_m"] == 3.0


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
    assert "and self._startup_gate_ready" in actor
    assert "from nav2_msgs.srv import ClearEntireCostmap" in actor
    assert "from std_srvs.srv import Empty" in actor
    assert 'declare_parameter("robot_reset_position_tolerance_m", 0.10)' in actor
    assert 'declare_parameter("startup_gate_timeout_s", 45.0)' in actor
    assert 'declare_parameter("task_reset_service", "/task_generator_node/reset_task")' in actor
    assert 'declare_parameter("task_reset_topic", "/task_generator_node/task_reset")' in actor
    assert "self._task_reset_client.call_async(Empty.Request())" in actor
    assert "if self._experiment_started:" in actor
    assert "refused task reset after experiment_started" in actor
    assert "observed authoritative TaskGenerator reset" in actor
    assert "Clock(clock_type=ClockType.STEADY_TIME)" in actor
    assert "if not self._task_reset_observed or not self._navigation_active:" in actor
    assert "if self._robot_pose_is_within_start_tolerance():" in actor
    assert "waiting for fresh Gazebo confirmation at configured start" in actor
    reset_advance = actor[
        actor.index("def _advance_robot_reset") : actor.index("def _advance_costmap_clear")
    ]
    assert "if self._robot_pose_is_within_start_tolerance():" in reset_advance
    assert "self._request_robot_reset" not in reset_advance
    assert "waiting for authoritative TaskGenerator pose convergence" in reset_advance
    assert "client.call_async(ClearEntireCostmap.Request())" in actor
    assert "startup gate cleared local and global Nav2 costmaps" in actor
    assert "startup gate failed; actors_healthy=false" in actor
    assert "if not self._advance_odometry_settle" in actor
    assert "startup gate rejecting reset-transient odometry" in actor
    assert 'declare_parameter("startup_odom_settle_s", 0.50)' in actor
    assert "def _actual_pedestrian_poses_are_fresh" in actor
    assert "self._actual_proxy_pose_received_s[name] = received_s" in actor
    assert "startup gate waiting for authoritative Gazebo pedestrian poses" in actor
    assert "Gazebo pedestrian poses remained missing or stale" in actor
    assert "elif self._experiment_started and len(self._spawn_validated)" in actor
    assert "self._actual_pose_received_s" not in actor
    assert '"${ramp_ros_prefix}/lib/ramp_ros/odom_tf_broadcaster"' in runtime
    assert '-p odom_topic:="${odom_topic}"' in runtime
    assert 'stop_pid_bounded "${odom_tf_pid}" INT 10' in runtime
    startup_gate = actor[actor.index("def _advance_startup_gate") : actor.index("def _on_odom")]
    assert startup_gate.index("if not self._advance_robot_reset") < startup_gate.index(
        "if not self._advance_odometry_settle"
    )
    odom_gate_index = startup_gate.index("if not self._advance_odometry_settle")
    actor_gate_index = startup_gate.index(
        "if not self._actual_pedestrian_poses_are_fresh", odom_gate_index
    )
    assert odom_gate_index < actor_gate_index
    assert actor_gate_index < startup_gate.index("if not self._advance_costmap_clear")
    assert startup_gate.index("if not self._advance_costmap_clear") < startup_gate.index(
        "self._startup_gate_ready = True"
    )
    assert 'robot_nav_namespace="${nav_action%/navigate_to_pose}"' in runtime
    assert (
        'local_costmap_clear_service="${robot_nav_namespace}/local_costmap/'
        'clear_entirely_local_costmap"' in runtime
    )
    assert (
        'global_costmap_clear_service="${robot_nav_namespace}/global_costmap/'
        'clear_entirely_global_costmap"' in runtime
    )
    assert '-p local_costmap_clear_service:="${local_costmap_clear_service}"' in runtime
    assert '-p global_costmap_clear_service:="${global_costmap_clear_service}"' in runtime
    assert "-p task_reset_service:=/task_generator_node/reset_task" in runtime
    assert "-p task_reset_topic:=/task_generator_node/task_reset" in runtime
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
    assert "deterministic simulator startup/actor health check failed" in logger
    assert "NavigateToPose did not activate within the startup deadline" in logger
    assert "episode start handshake did not complete before the wall-clock deadline" in logger
    assert runtime.count("episode_start_topic:=/ramp/episode_started") == 4
    assert runtime.count("logger_ready_topic:=/ramp/logger_ready") == 2
    assert runtime.count("odometry_is_world_frame:=true") == 4


def test_known_pose_gazebo_uses_dynamic_odom_base_transform_only() -> None:
    root = Path(__file__).resolve().parents[2]
    container = (root / "scripts/bootstrap/arena_container.sh").read_text(encoding="utf-8")
    patch = (root / "third_party/task_generator_known_pose_gazebo_tf.patch").read_text(
        encoding="utf-8"
    )
    marker = "ramp_ros publishes the dynamic odom-to-base transform"
    assert "task_generator_known_pose_gazebo_tf.patch" in container
    assert f'grep -q "{marker}" "$robot_manager"' in container
    assert "Arena known-pose Gazebo TF patch is not applied" in container
    assert marker in patch
    assert (
        "+        if self.node.conf.Arena.SIM.value not in (Constants.SimSimulator.GAZEBO,):"
    ) in patch
    assert "+            self._odom_base_transform()" in patch


def test_episode_cleanup_is_bounded_for_every_auxiliary_process() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "scripts/arena/run_baseline_episode_inner.sh").read_text(encoding="utf-8")
    assert "stop_pid_bounded" in runtime
    assert 'stop_pid_bounded "${recovery_node_pid}" INT 10' in runtime
    assert 'stop_pid_bounded "${actor_pid}" INT 10' in runtime
    assert 'kill -KILL "${pid}"' in runtime
    assert 'RAMP_DISABLE_AUTO_RESET:-0}" != "1"' in runtime


def test_tf_diagnostic_uses_authoritative_odometry_broadcaster() -> None:
    root = Path(__file__).resolve().parents[2]
    diagnostic = (root / "scripts/arena/diagnose_tf_inner.sh").read_text(encoding="utf-8")
    assert 'ramp_ros_prefix="$(ros2 pkg prefix ramp_ros)"' in diagnostic
    assert '"${ramp_ros_prefix}/lib/ramp_ros/odom_tf_broadcaster"' in diagnostic
    assert "-p odom_topic:=/task_generator_node/jackal/odom" in diagnostic
    assert "grep -Fq 'broadcast first odometry transform'" in diagnostic
    assert 'stop_pid_bounded "${odom_tf_pid}" INT 10' in diagnostic
    assert 'kill -KILL "${pid}"' in diagnostic
    assert diagnostic.index("odom_tf_broadcaster") < diagnostic.index("printf 'TF_ODOM_BASE")


def test_episode_logger_rejects_privileged_robot_pose_jumps() -> None:
    root = Path(__file__).resolve().parents[2]
    logger = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py").read_text()
    assert 'declare_parameter("maximum_privileged_pose_jump_m", 1.0)' in logger
    assert "Gazebo robot pose jumped during the active episode" in logger
    assert "if starting:" in logger
    assert "self._privileged_robot_pose = None" in logger
    assert "math.dist(new_pose[:2], self._privileged_robot_pose[:2])" in logger
    assert 'declare_parameter("physical_goal_tolerance_m", 0.30)' in logger
    assert 'declare_parameter("goal_confirmation_timeout_s", 1.0)' in logger
    assert "localized goal success disagrees with Gazebo robot pose" in logger
    assert logger.count("self._confirm_goal_reached(") == 3
    assert "self._pending_goal_start_wall_s" in logger
    assert 'or "unspecified_recovery_failure"' in logger
    assert "recovery manager exhausted the configured recovery attempts" not in logger


def test_recovery_safety_has_omnidirectional_footprint_guard() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    assert manager.count("footprint_stop_clearance_m") >= 3
    assert manager.count("_footprint_stop_distance(") >= 3
    assert manager.count("_motion_stop_distance(") >= 3
    config = yaml.safe_load((root / "configs/failure/recovery_state_machine.yaml").read_text())
    assert config["footprint_stop_clearance_m"] == 0.48
    assert config["collision_latched_stop_clearance_m"] == 0.85
    assert config["collision_latched_action_clearance_m"] == 0.90
    assert config["collision_latched_stop_clearance_m"] > config["footprint_stop_clearance_m"]
    assert config["collision_latched_action_clearance_m"] >= (
        config["collision_latched_stop_clearance_m"] + config["emergency_release_hysteresis_m"]
    )
    assert config["maximum_recovery_path_deviation_m"] == 0.6
    assert config["recurrent_escape_maximum_path_deviation_m"] == 1.5
    assert (
        config["recurrent_escape_maximum_path_deviation_m"]
        > config["maximum_recovery_path_deviation_m"]
    )
    assert config["maximum_recovery_sequence_duration_s"] == 45.0
    assert config["backup_minimum_duration_s"] == 0.8
    assert config["backup_maximum_duration_s"] == 3.0
    assert config["backup_clearance_improvement_m"] == 0.25
    assert config["backup_mask_validated_distance_m"] == 0.45
    assert (
        config["backup_speed_mps"] * config["backup_maximum_duration_s"]
        <= config["backup_mask_validated_distance_m"]
    )
    assert config["emergency_rotation_clearance_m"] == 0.24
    assert config["emergency_turn_duration_s"] == 0.8
    assert config["emergency_maximum_turn_pulses"] == 4
    assert config["emergency_maximum_turn_pulses"] * config["emergency_turn_duration_s"] * config[
        "emergency_turn_speed_radps"
    ] == pytest.approx(1.92)
    assert max(
        config["emergency_rotation_clearance_m"],
        config["footprint_stop_clearance_m"] + config["emergency_release_hysteresis_m"],
    ) == pytest.approx(0.53)
    assert config["emergency_forward_entry_clearance_m"] == 0.85
    assert config["emergency_backup_reset_clear_s"] == 3.0
    assert config["emergency_minimum_retreat_pulses"] == 3
    assert config["emergency_minimum_retreat_pulses"] * config[
        "emergency_backup_duration_s"
    ] * config["backup_speed_mps"] == pytest.approx(0.36)
    assert config["emergency_maximum_improving_backups"] == 8
    assert config["emergency_backup_progress_m"] == 0.05
    assert config["emergency_translation_clearance_m"] == 0.36
    assert config["bc_wait_budget_decisions"] == 3
    assert config["bc_backup_budget_decisions"] == 4
    assert config["bc_replan_budget_decisions"] == 1
    assert config["bc_recurrent_escape_after_recoveries"] == 1
    assert config["recurrent_escape_minimum_lateral_displacement_m"] == 0.25
    assert config["bc_progress_reset_m"] == 0.25
    assert config["bc_maximum_net_retreat_m"] == 1.4
    assert config["bc_subgoal_retry_budget_decisions"] == 4
    assert config["bc_subgoal_stall_displacement_m"] == 0.08
    assert config["bc_action_interval_s"] == 0.5
    assert config["subgoal_settle_s"] == 1.0
    assert config["bc_subgoal_minimum_execution_s"] == 2.0
    assert config["bc_subgoal_maximum_duration_s"] == 6.0
    assert (
        config["subgoal_settle_s"] + config["bc_subgoal_minimum_execution_s"]
        < config["bc_subgoal_maximum_duration_s"]
        < config["maximum_recovery_duration_s"]
    )
    assert config["bc_rejoin_block_threshold"] == 0.65
    assert config["bc_yield_release_clearance_m"] == 1.25
    assert config["bc_yield_release_frames"] == 3
    assert config["bc_yield_forward_half_width_degrees"] == 45.0
    assert config["bc_yield_maximum_forward_progress_m"] == 0.10
    assert config["bc_closing_side_sector_min_degrees"] == 5.0
    assert config["bc_closing_side_sector_max_degrees"] == 60.0
    assert config["bc_closing_side_delta_m"] == 0.20
    assert config["bc_closing_side_maximum_range_m"] == 4.0
    assert config["bc_closing_side_minimum_beams"] == 5
    assert config["bc_closing_side_maximum_angular_speed_radps"] == 0.20
    assert '"bc_yield_release_clearance_m": 1.25' in manager
    assert '"bc_yield_release_frames": 3' in manager
    assert '"bc_yield_forward_half_width_degrees": 45.0' in manager
    assert '"bc_yield_maximum_forward_progress_m": 0.10' in manager
    assert '"bc_closing_side_sector_min_degrees": 5.0' in manager
    assert '"bc_closing_side_sector_max_degrees": 60.0' in manager
    assert '"bc_closing_side_delta_m": 0.20' in manager
    assert '"bc_closing_side_maximum_range_m": 4.0' in manager
    assert '"bc_closing_side_minimum_beams": 5' in manager
    assert '"bc_closing_side_maximum_angular_speed_radps": 0.20' in manager
    assert "ObservableClosingSideLatch()" in manager
    assert "constrain_task_lateral_sides(" in manager
    assert manager.count("self._bc_closing_side_latch.reset()") >= 3
    assert "latched_right={int(self._bc_closing_side_latch.right_occupied)}" in manager
    assert "latched_left={int(self._bc_closing_side_latch.left_occupied)}" in manager
    assert '"emergency_rotation_clearance_m": 0.24' in manager
    assert '"emergency_turn_duration_s": 0.8' in manager
    assert '"emergency_maximum_turn_pulses": 4' in manager
    assert "self._effective_emergency_rotation_clearance()" in manager
    assert '"collision_latched_stop_clearance_m": 0.85' in manager
    assert '"collision_latched_action_clearance_m": 0.90' in manager
    assert "the latched margin is" in manager
    assert '"emergency_backup_reset_clear_s": 3.0' in manager
    assert '"emergency_minimum_retreat_pulses": 3' in manager
    assert '"backup_maximum_duration_s": 3.0' in manager
    assert '"maximum_recovery_sequence_duration_s": 45.0' in manager
    assert '"bc_recurrent_escape_after_recoveries": 1' in manager
    assert '"recurrent_escape_maximum_path_deviation_m": 1.5' in manager
    assert manager.count("self._effective_recovery_path_deviation()") == 2
    assert "self._bc_yield_latch.latched" in manager
    assert '"recurrent_escape_minimum_lateral_displacement_m": 0.25' in manager
    assert '"bc_subgoal_minimum_execution_s": 2.0' in manager
    assert '"bc_subgoal_maximum_duration_s": 6.0' in manager
    assert "BoundedSubgoalOption(" in manager
    assert "self._bc_subgoal_option.is_complete(" in manager
    assert "maximum_recovery_sequence_duration_s=self._float(" in manager
    assert "BoundedBackupOption(" in manager
    assert "self._backup_start_clearance_m" in manager
    assert 'backup_distance_m=self._float("backup_mask_validated_distance_m")' in manager
    assert "apply_observable_scan_mask(" in manager
    assert manager.count("_forward_escape_clearance()") >= 2
    assert 'translation_clearance = self._float("emergency_translation_clearance_m")' in manager
    assert 'self._float("collision_latched_stop_clearance_m")' in manager
    assert "self._task_corridor_path or self._path" in manager
    assert manager.count("collision_latched_motion_clearance(") == 2
    assert "constrain_repeated_backup(" in manager
    assert "constrain_net_retreat(" in manager
    assert "constrain_stalled_subgoals(" in manager
    assert "ensure_safe_wait_fallback(mask)" in manager
    learned_selection = manager.index("def _select_decision(")
    budget_constraint_order = (
        manager.index("mask = constrain_repeated_replan(", learned_selection),
        manager.index("mask = constrain_repeated_backup(", learned_selection),
        manager.index("mask = constrain_net_retreat(", learned_selection),
        manager.index("mask = constrain_stalled_wait(", learned_selection),
        manager.index("mask = self._constrain_bc_recurrent_escape(", learned_selection),
        manager.index("mask = ensure_safe_wait_fallback(mask)", learned_selection),
    )
    assert budget_constraint_order == tuple(sorted(budget_constraint_order))
    closing_constraint_order = (
        manager.index("mask = constrain_directional_yield_motion(", learned_selection),
        manager.index("closing_side_result = self._constrain_bc_temporal_closing_side("),
        manager.index("mask = self._constrain_bc_recurrent_escape(", learned_selection),
    )
    assert closing_constraint_order == tuple(sorted(closing_constraint_order))
    assert "right_beams={result.right_closing_beams}" in manager
    assert "left_beams={result.left_closing_beams}" in manager
    assert "emergency_backup_permitted &= self._bc_retreat_guard.backup_permitted(" in manager
    assert "footprint_clearance_m=motion_clearance" in manager
    detector = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/failure_detector_node.py").read_text()
    assert "RecoveryDecision.EMERGENCY_STOP" in detector
    assert "timestamp <= self._last_timestamp" in detector
    labeler = (root / "scripts/data/label_expert.py").read_text()
    assert '"--collision-latched-action-clearance", type=float, default=0.90' in labeler
    assert '"--maximum-recovery-path-deviation", type=float, default=0.60' in labeler
    assert "allow_initial_overlap_when_separating=collision_latched" in labeler
    assert detector.count("self._detector.reset()") == 1
    assert 'self.declare_parameter("wait_for_episode_start", False)' in detector
    assert "def _on_episode_start(self, message: Bool)" in detector
    assert "if not self._episode_started:" in detector
    assert 'self.declare_parameter("maximum_valid_linear_speed_mps", 2.0)' in detector
    assert 'self.declare_parameter("maximum_valid_angular_speed_radps", 4.0)' in detector
    assert 'self.declare_parameter("motion_rule_startup_grace_s", 4.0)' in detector
    assert "abs(linear_velocity)" in detector
    assert "timestamp - self._episode_started_at_s" in detector


def test_oracle_rejoin_distinguishes_hard_risk_from_soft_latch() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    expert_config = yaml.safe_load((root / "configs/expert/default.yaml").read_text())
    failure_config = yaml.safe_load(
        (root / "configs/failure/recovery_state_machine.yaml").read_text()
    )
    assert "expert_rejoin_block_threshold" not in manager
    assert "rejoin_block_collision_threshold" not in expert_config
    assert failure_config["tau_on"] == pytest.approx(0.65)
    assert "release_threshold=self._machine.config.tau_on" in manager
    assert 'release_threshold=self._float("bc_rejoin_block_threshold")' in manager


def test_oracle_yield_escape_is_planning_masked_and_reports_cause() -> None:
    root = Path(__file__).resolve().parents[2]
    manager = (root / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py").read_text()
    retreat_update = manager.index("self._oracle_yield.require_escape_if_retreat_unavailable(")
    recurrent_mask = manager.index("mask = constrain_recurrent_yield_escape(", retreat_update)
    expert_label = manager.index("label = PlanningRecoveryExpert(grid).label(", recurrent_mask)
    assert retreat_update < recurrent_mask < expert_label
    assert "retreat_is_safe=backup_mask_legal" in manager
    assert "mask[BACKUP_ACTION_ID] = False" in manager
    assert "f\"cause={self._oracle_yield.escape_reason or 'unspecified'} \"" in manager
