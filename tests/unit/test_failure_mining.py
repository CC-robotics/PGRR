import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "mine_failures.py"
_SPEC = importlib.util.spec_from_file_location("ramp_mine_failures", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
MAX_SAFE_ROS_DOMAIN_ID = _MODULE.MAX_SAFE_ROS_DOMAIN_ID
_ros_domain_id = _MODULE._ros_domain_id


def test_ros_domain_id_stays_in_safe_range_for_large_seed_sets() -> None:
    domains = [_ros_domain_id(200, seed, attempt, 3) for seed in range(100) for attempt in range(3)]
    assert min(domains) >= 1
    assert max(domains) <= MAX_SAFE_ROS_DOMAIN_ID


def test_ros_domain_id_is_deterministic_and_separates_adjacent_attempts() -> None:
    assert _ros_domain_id(20, 19, 2, 3) == _ros_domain_id(20, 19, 2, 3)
    assert _ros_domain_id(20, 19, 1, 3) != _ros_domain_id(20, 19, 2, 3)
