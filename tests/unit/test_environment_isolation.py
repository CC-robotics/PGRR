import os


def test_offline_tests_do_not_inherit_ros_pythonpath() -> None:
    pythonpath = os.environ.get("PYTHONPATH", "")
    assert "/opt/ros/" not in pythonpath
