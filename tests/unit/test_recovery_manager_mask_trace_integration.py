from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANAGER = ROOT / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
WRAPPER = ROOT / "scripts/arena/run_baseline_episode.sh"
RUNTIME = ROOT / "scripts/arena/run_baseline_episode_inner.sh"


def test_upstream_mask_trace_is_opt_in_and_covers_three_layers() -> None:
    source = MANAGER.read_text(encoding="utf-8")

    assert 'self.declare_parameter("enable_upstream_mask_trace", False)' in source
    assert "MaskTraceRecorder(enabled=self._upstream_mask_trace_enabled)" in source
    stages = (
        source.index('recorder.record("map_connectivity"'),
        source.index('recorder.record("observable_scan"'),
        source.index('recorder.record("path_corridor"'),
    )
    assert stages == tuple(sorted(stages))


def test_disabled_trace_preserves_reason_and_enabled_trace_preserves_decision_fields() -> None:
    source = MANAGER.read_text(encoding="utf-8")
    helper = source[source.index("    def _with_upstream_mask_trace(") :]

    assert "if not self._last_upstream_mask_trace:" in helper
    assert "return decision" in helper
    assert "decision.action_id" in helper
    assert "decision.confidence" in helper
    assert 'f"{self._last_upstream_mask_trace}; {decision.reason}"' in helper


def test_trace_is_captured_before_special_action_availability_is_finalized() -> None:
    source = MANAGER.read_text(encoding="utf-8")
    action_mask = source[
        source.index("    def _action_mask(") : source.index("    def _expert_decision(")
    ]

    trace_end = action_mask.index("self._last_upstream_mask_trace = recorder.as_reason()")
    replan_finalize = action_mask.index("mask[REPLAN_ACTION_ID] &= self._adapter.ready")
    wait_finalize = action_mask.index("mask[WAIT_ACTION_ID] = True")
    continue_finalize = action_mask.index("mask[CONTINUE_ACTION_ID] = True")
    assert trace_end < replan_finalize < wait_finalize < continue_finalize


def test_trace_records_original_scan_predicate_pass_sets_only_when_enabled() -> None:
    source = MANAGER.read_text(encoding="utf-8")
    action_mask = source[
        source.index("    def _action_mask(") : source.index("    def _expert_decision(")
    ]

    assert "{} if self._upstream_mask_trace_enabled else None" in action_mask
    assert "diagnostics=scan_diagnostics" in action_mask
    assert "mask_scan_predicates directional_pass=" in action_mask
    assert "capsule_pass={capsule_text}" in action_mask
    assert "target_clearance_m={action_clearance:.3f}" in action_mask
    assert "swept_clearance_m={swept_clearance:.3f}" in action_mask
    assert "capsule_failures={failure_text}" in action_mask
    assert "capsule_min_m={minimum_text}" in action_mask
    assert "capsule_fraction={fraction_text}" in action_mask


def test_train_only_runner_exposes_validated_opt_in_switch() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert 'mask_trace="${RAMP_ENABLE_UPSTREAM_MASK_TRACE:-0}"' in wrapper
    assert "RAMP_ENABLE_UPSTREAM_MASK_TRACE must be 0 or 1" in wrapper
    assert (
        'optional_runtime_environment+=("RAMP_ENABLE_UPSTREAM_MASK_TRACE=${mask_trace}")'
        in wrapper
    )
    assert 'ENABLE_UPSTREAM_MASK_TRACE="${RAMP_ENABLE_UPSTREAM_MASK_TRACE:-0}"' in runtime
    assert "RAMP_ENABLE_UPSTREAM_MASK_TRACE must be 0 or 1" in runtime
    assert "upstream_mask_trace_ros_value=false" in runtime
    assert 'if [[ "${ENABLE_UPSTREAM_MASK_TRACE}" == "1" ]]' in runtime
    assert "upstream_mask_trace_ros_value=true" in runtime
    assert '-p enable_upstream_mask_trace:="${upstream_mask_trace_ros_value}"' in runtime
