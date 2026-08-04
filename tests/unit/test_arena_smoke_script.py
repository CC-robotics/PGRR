from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/arena/smoke_arena.sh"
SMOKE = ROOT / "scripts/arena/smoke_runtime_inner.sh"


def test_smoke_requires_samples_instead_of_accepting_idle_topics() -> None:
    source = SMOKE.read_text(encoding="utf-8")

    assert "wait_for_topic_sample()" in source
    assert 'done < <(topics_by_type "${type}")' in source
    assert 'timeout 4 ros2 topic echo --once "${candidate}"' in source
    assert 'odom_topic="$(wait_for_topic_sample nav_msgs/msg/Odometry)"' in source
    assert 'odom_topic="$(wait_for_discovery topic nav_msgs/msg/Odometry)"' not in source


def test_smoke_mounts_the_pinned_jackal_mapping() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert "export RAMP_ENABLE_CMD_MUX=1" in source
    assert "scripts/bootstrap/arena_container.sh" in source
