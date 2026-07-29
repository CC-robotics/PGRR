"""Deterministic Gazebo actor motion fallback for Arena Humble scenarios."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from geometry_msgs.msg import Pose, PoseArray, Quaternion
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import SetEntityPose, SpawnEntity


@dataclass(frozen=True, slots=True)
class ActorRoute:
    name: str
    points: tuple[tuple[float, float], ...]
    speed: float

    @property
    def segment_lengths(self) -> tuple[float, ...]:
        cyclic = (*self.points, self.points[0])
        return tuple(
            math.dist(cyclic[index], cyclic[index + 1]) for index in range(len(self.points))
        )

    def pose_at(self, elapsed: float) -> tuple[float, float, float]:
        lengths = self.segment_lengths
        total = sum(lengths)
        if total <= 1.0e-6:
            return self.points[0][0], self.points[0][1], 0.0
        distance = (elapsed * self.speed) % total
        cyclic = (*self.points, self.points[0])
        for index, length in enumerate(lengths):
            if distance <= length or index == len(lengths) - 1:
                fraction = 0.0 if length <= 1.0e-6 else distance / length
                x0, y0 = cyclic[index]
                x1, y1 = cyclic[index + 1]
                return (
                    x0 + fraction * (x1 - x0),
                    y0 + fraction * (y1 - y0),
                    math.atan2(y1 - y0, x1 - x0),
                )
            distance -= length
        raise RuntimeError("unreachable route interpolation state")


def _quaternion(yaw: float) -> Quaternion:
    message = Quaternion()
    message.z = math.sin(yaw / 2.0)
    message.w = math.cos(yaw / 2.0)
    return message


class ScenarioActorController(Node):
    def __init__(self) -> None:
        super().__init__("scenario_actor_controller")
        self.declare_parameter("scenario_file", "")
        self.declare_parameter("set_pose_service", "/world/default/set_pose")
        self.declare_parameter("spawn_service", "/world/default/create")
        self.declare_parameter("privileged_humans_topic", "/ramp/privileged/humans")
        self.declare_parameter("update_frequency_hz", 2.0)
        scenario_path = Path(str(self.get_parameter("scenario_file").value))
        if not scenario_path.is_file():
            raise ValueError(f"scenario_file is not readable: {scenario_path}")
        self._routes = self._load_routes(scenario_path)
        if not self._routes:
            raise ValueError("scenario contains no dynamic actors")
        service_name = str(self.get_parameter("set_pose_service").value)
        self._client = self.create_client(SetEntityPose, service_name)
        spawn_service = str(self.get_parameter("spawn_service").value)
        self._spawn_client = self.create_client(SpawnEntity, spawn_service)
        self._publisher = self.create_publisher(
            PoseArray, str(self.get_parameter("privileged_humans_topic").value), 10
        )
        frequency = float(self.get_parameter("update_frequency_hz").value)
        if frequency <= 0.0:
            raise ValueError("update_frequency_hz must be positive")
        self._start_time: float | None = None
        self._pending: dict[str, Any] = {}
        self._spawn_pending: dict[str, Any] = {}
        self._spawn_attempted: set[str] = set()
        self._update_timer = self.create_timer(1.0 / frequency, self._update)
        self.get_logger().info(
            f"loaded {len(self._routes)} deterministic actor routes; service={service_name}"
        )

    @staticmethod
    def _proxy_sdf(name: str) -> str:
        return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>true</static>
    <link name="body">
      <pose>0 0 0.85 0 0 0</pose>
      <collision name="collision">
        <geometry><cylinder><radius>0.35</radius><length>1.70</length></cylinder></geometry>
      </collision>
      <visual name="visual">
        <geometry><cylinder><radius>0.35</radius><length>1.70</length></cylinder></geometry>
        <material><ambient>0.85 0.25 0.12 1</ambient><diffuse>0.85 0.25 0.12 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>"""

    @staticmethod
    def _load_routes(path: Path) -> tuple[ActorRoute, ...]:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        routes: list[ActorRoute] = []
        for actor in scenario.get("obstacles", {}).get("dynamic", []):
            points = tuple((float(point[0]), float(point[1])) for point in actor["waypoints"])
            if not points:
                continue
            routes.append(
                ActorRoute(
                    name=str(actor["name"]),
                    points=points,
                    speed=float(actor.get("max_vel", 0.4)),
                )
            )
        return tuple(routes)

    def _update(self) -> None:
        if not self._client.service_is_ready() or not self._spawn_client.service_is_ready():
            self.get_logger().warning(
                "Gazebo entity services are not ready", throttle_duration_sec=5.0
            )
            return
        now = self.get_clock().now().nanoseconds * 1.0e-9
        if self._start_time is None:
            self._start_time = now
        elapsed = now - self._start_time
        pose_array = PoseArray()
        pose_array.header.stamp = self.get_clock().now().to_msg()
        pose_array.header.frame_id = "map"
        for route in self._routes:
            x, y, yaw = route.pose_at(elapsed)
            pose = Pose()
            pose.position.x = x
            pose.position.y = y
            pose.orientation = _quaternion(yaw)
            pose_array.poses.append(pose)
            if route.name not in self._spawn_attempted:
                request = SpawnEntity.Request()
                request.entity_factory.name = route.name
                request.entity_factory.allow_renaming = False
                request.entity_factory.sdf = self._proxy_sdf(route.name)
                request.entity_factory.pose = pose
                request.entity_factory.relative_to = "world"
                self._spawn_pending[route.name] = self._spawn_client.call_async(request)
                self._spawn_attempted.add(route.name)
                continue
            spawn_pending = self._spawn_pending.get(route.name)
            if spawn_pending is not None and not spawn_pending.done():
                continue
            pending = self._pending.get(route.name)
            if pending is not None and not pending.done():
                continue
            request = SetEntityPose.Request()
            request.entity.name = route.name
            request.entity.type = Entity.MODEL
            request.pose = pose
            self._pending[route.name] = self._client.call_async(request)
        self._publisher.publish(pose_array)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: ScenarioActorController | None = None
    try:
        node = ScenarioActorController()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
