"""Top-level launch placeholder with configurable namespace and simulation time."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("config", default_value=""),
        ]
    )
