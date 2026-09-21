from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "ros_ws/src/ramp_ros/ramp_ros/nodes/recovery_manager_node.py"
WRAPPER = ROOT / "scripts/arena/run_baseline_episode.sh"
RUNTIME = ROOT / "scripts/arena/run_baseline_episode_inner.sh"


def _source() -> str:
    return NODE.read_text(encoding="utf-8")


def test_observation_shadow_is_declared_default_off_and_bounded() -> None:
    source = _source()

    assert 'self.declare_parameter("enable_observation_shadow", False)' in source
    assert "ObservationShadowComparator(" in source
    assert 'enabled=bool(self.get_parameter("enable_observation_shadow").value)' in source
    assert "ObservationShadowAccumulator()" in source


def test_observation_shadow_keeps_reference_authoritative() -> None:
    source = _source()
    start = source.index("    def _observation(")
    end = source.index("    def _laser_clearance(", start)
    method = source[start:end]

    reference = method.index("reference = RecoveryObservation(")
    comparison = method.index("self._observation_shadow.compare(")
    record = method.index("self._observation_shadow_summary.record(comparison)")
    returned = method.index("return reference")
    assert reference < comparison < record < returned
    assert "return candidate" not in method


def test_shadow_candidate_uses_only_deployable_snapshots() -> None:
    source = _source()
    start = source.index("    def _observation(")
    end = source.index("    def _laser_clearance(", start)
    method = source[start:end]

    assert "RecoveryObservationBuilder.build(" in method
    assert "task_path=tuple(self._path)" in method
    assert "distance_history=list(self._distance_history)" in method
    assert "angular_velocity_history=list(self._angular_history)" in method
    assert "privileged" not in method
    assert "humans" not in method


def test_standard_runner_forwards_validated_default_off_shadow_switch() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert 'observation_shadow="${RAMP_ENABLE_OBSERVATION_SHADOW:-0}"' in wrapper
    assert "RAMP_ENABLE_OBSERVATION_SHADOW must be 0 or 1" in wrapper
    assert (
        'optional_runtime_environment+=("RAMP_ENABLE_OBSERVATION_SHADOW=${observation_shadow}")'
        in wrapper
    )
    assert 'ENABLE_OBSERVATION_SHADOW="${RAMP_ENABLE_OBSERVATION_SHADOW:-0}"' in runtime
    assert "observation_shadow_ros_value=false" in runtime
    assert 'if [[ "${ENABLE_OBSERVATION_SHADOW}" == "1" ]]' in runtime
    assert "observation_shadow_ros_value=true" in runtime
    assert '-p enable_observation_shadow:="${observation_shadow_ros_value}"' in runtime


def test_enabled_shadow_emits_one_bounded_summary_at_shutdown() -> None:
    source = NODE.read_text(encoding="utf-8")

    assert "def destroy_node(self) -> bool:" in source
    assert "self._observation_shadow.enabled" in source
    assert "self._observation_shadow_summary_logged = True" in source
    assert '"observation_shadow_summary="' in source
    assert "self._observation_shadow_summary.as_dict()" in source
    assert "return super().destroy_node()" in source
