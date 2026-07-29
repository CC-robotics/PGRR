from setuptools import find_packages, setup

package_name = "ramp_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/ramp_ros"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RAMP Research",
    maintainer_email="ramp-local@example.com",
    description="ROS2 adapters and nodes for failure-triggered recovery",
    license="MIT",
    entry_points={
        "console_scripts": [
            "episode_logger = ramp_ros.nodes.episode_logger_node:main",
            "scenario_actor_controller = ramp_ros.nodes.scenario_actor_controller_node:main",
        ]
    },
)
