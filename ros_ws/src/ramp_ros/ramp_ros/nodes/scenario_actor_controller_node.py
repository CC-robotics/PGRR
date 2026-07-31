"""Deterministic Gazebo actor motion fallback for Arena Humble scenarios."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Pose, PoseArray, PoseStamped, Quaternion
from nav_msgs.msg import Odometry
from ramp_core.evaluation.navigation import navigation_status_is_active
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import SetEntityPose, SpawnEntity
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage


@dataclass(frozen=True, slots=True)
class ActorRoute:
    name: str
    points: tuple[tuple[float, float], ...]
    speed: float
    cyclic: bool = True
    robot_avoidance_distance_m: float = 1.3

    def __post_init__(self) -> None:
        if self.robot_avoidance_distance_m <= 0.71:
            raise ValueError("robot avoidance distance must exceed combined collision radii")

    @property
    def segment_lengths(self) -> tuple[float, ...]:
        route_points = (*self.points, self.points[0]) if self.cyclic else self.points
        return tuple(
            math.dist(route_points[index], route_points[index + 1])
            for index in range(len(route_points) - 1)
        )

    def pose_at(self, elapsed: float) -> tuple[float, float, float]:
        lengths = self.segment_lengths
        total = sum(lengths)
        if total <= 1.0e-6:
            return self.points[0][0], self.points[0][1], 0.0
        travelled = max(0.0, elapsed) * self.speed
        distance = travelled % total if self.cyclic else min(travelled, total)
        route_points = (*self.points, self.points[0]) if self.cyclic else self.points
        for index, length in enumerate(lengths):
            if distance <= length or index == len(lengths) - 1:
                fraction = 0.0 if length <= 1.0e-6 else distance / length
                x0, y0 = route_points[index]
                x1, y1 = route_points[index + 1]
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
        self.declare_parameter("privileged_robot_pose_topic", "/ramp/privileged/robot_pose")
        self.declare_parameter("actual_robot_name", "jackal")
        self.declare_parameter("actual_pose_topic", "/world/default/dynamic_pose/info")
        self.declare_parameter("actual_pose_timeout_s", 1.0)
        self.declare_parameter("health_topic", "/ramp/actors_healthy")
        self.declare_parameter("episode_start_topic", "/ramp/episode_started")
        self.declare_parameter("logger_ready_topic", "/ramp/logger_ready")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("nav_status_topic", "navigate_to_pose/_action/status")
        self.declare_parameter("wait_for_navigation_active", False)
        self.declare_parameter("update_native_actors", False)
        self.declare_parameter("robot_start_x", 0.0)
        self.declare_parameter("robot_start_y", 0.0)
        self.declare_parameter("robot_start_yaw", 0.0)
        self.declare_parameter("robot_avoidance_distance_m", 1.3)
        self.declare_parameter("update_frequency_hz", 2.0)
        self.declare_parameter("pose_update_timeout_s", 2.0)
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
        self._robot_pose_publisher = self.create_publisher(
            PoseStamped, str(self.get_parameter("privileged_robot_pose_topic").value), 10
        )
        self._health_publisher = self.create_publisher(
            Bool, str(self.get_parameter("health_topic").value), 10
        )
        self._start_publisher = self.create_publisher(
            Bool, str(self.get_parameter("episode_start_topic").value), 10
        )
        frequency = float(self.get_parameter("update_frequency_hz").value)
        if frequency <= 0.0:
            raise ValueError("update_frequency_hz must be positive")
        if float(self.get_parameter("robot_avoidance_distance_m").value) <= 0.71:
            raise ValueError("robot_avoidance_distance_m must exceed combined collision radii")
        self._robot_position: tuple[float, float] | None = None
        self._last_update_s: float | None = None
        self._wait_for_navigation_active = bool(
            self.get_parameter("wait_for_navigation_active").value
        )
        self._navigation_active = not self._wait_for_navigation_active
        self._experiment_started = not self._wait_for_navigation_active
        self._logger_ready = not self._wait_for_navigation_active
        self._route_elapsed = {route.name: 0.0 for route in self._routes}
        self._pending: dict[str, Any] = {}
        self._pending_since_s: dict[str, float] = {}
        self._pending_target_elapsed: dict[str, float] = {}
        self._spawn_pending: dict[str, Any] = {}
        self._spawn_attempted: set[str] = set()
        self._spawn_validated: set[str] = set()
        self._actual_proxy_poses: dict[str, Pose] = {}
        self._actual_robot_pose: Pose | None = None
        self._actual_pose_received_s: float | None = None
        self._actual_pose_wait_since_s: float | None = None
        self._healthy = True
        self._odom_subscription = self.create_subscription(
            Odometry,
            str(self.get_parameter("odom_topic").value),
            self._on_odom,
            qos_profile_sensor_data,
        )
        self._status_subscription = self.create_subscription(
            GoalStatusArray,
            str(self.get_parameter("nav_status_topic").value),
            self._on_status,
            10,
        )
        self._logger_ready_subscription = self.create_subscription(
            Bool,
            str(self.get_parameter("logger_ready_topic").value),
            self._on_logger_ready,
            10,
        )
        self._actual_pose_subscription = self.create_subscription(
            TFMessage,
            str(self.get_parameter("actual_pose_topic").value),
            self._on_actual_poses,
            qos_profile_sensor_data,
        )
        self._update_timer = self.create_timer(1.0 / frequency, self._update)
        self.get_logger().info(
            f"loaded {len(self._routes)} deterministic actor routes; service={service_name}"
        )

    @staticmethod
    def _proxy_sdf(name: str) -> str:
        return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>false</static>
    <link name="body">
      <pose>0 0 0.85 0 0 0</pose>
      <gravity>false</gravity>
      <kinematic>false</kinematic>
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>0.25</ixx><iyy>0.25</iyy><izz>0.06</izz>
          <ixy>0.0</ixy><ixz>0.0</ixz><iyz>0.0</iyz>
        </inertia>
      </inertial>
      <visual name="visual">
        <geometry><cylinder><radius>0.35</radius><length>1.70</length></cylinder></geometry>
        <material><ambient>0.85 0.25 0.12 1</ambient><diffuse>0.85 0.25 0.12 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>"""

    @staticmethod
    def _proxy_name(actor_name: str) -> str:
        return f"ramp_lidar_proxy_{actor_name}"

    def _on_odom(self, message: Odometry) -> None:
        if self._actual_robot_pose is not None:
            self._robot_position = (
                float(self._actual_robot_pose.position.x),
                float(self._actual_robot_pose.position.y),
            )
            return
        local_x = float(message.pose.pose.position.x)
        local_y = float(message.pose.pose.position.y)
        start_x = float(self.get_parameter("robot_start_x").value)
        start_y = float(self.get_parameter("robot_start_y").value)
        start_yaw = float(self.get_parameter("robot_start_yaw").value)
        self._robot_position = (
            start_x + math.cos(start_yaw) * local_x - math.sin(start_yaw) * local_y,
            start_y + math.sin(start_yaw) * local_x + math.cos(start_yaw) * local_y,
        )

    def _on_status(self, message: GoalStatusArray) -> None:
        if self._navigation_active:
            return
        if not navigation_status_is_active(
            tuple(int(item.status) for item in message.status_list),
            accepted=int(GoalStatus.STATUS_ACCEPTED),
            executing=int(GoalStatus.STATUS_EXECUTING),
            canceling=int(GoalStatus.STATUS_CANCELING),
        ):
            return
        self._navigation_active = True
        self._route_elapsed = {route.name: 0.0 for route in self._routes}
        self._last_update_s = self.get_clock().now().nanoseconds * 1.0e-9
        self.get_logger().info("navigation activated; waiting for episode logger handshake")

    def _on_logger_ready(self, message: Bool) -> None:
        self._logger_ready |= bool(message.data)

    def _on_actual_poses(self, message: TFMessage) -> None:
        expected = {self._proxy_name(route.name) for route in self._routes}
        robot_name = str(self.get_parameter("actual_robot_name").value)
        received = False
        for transform in message.transforms:
            name = transform.child_frame_id
            if name not in expected and name != robot_name:
                continue
            pose = Pose()
            pose.position.x = transform.transform.translation.x
            pose.position.y = transform.transform.translation.y
            pose.position.z = transform.transform.translation.z
            pose.orientation = transform.transform.rotation
            if name == robot_name:
                self._actual_robot_pose = pose
                self._robot_position = (float(pose.position.x), float(pose.position.y))
            else:
                self._actual_proxy_poses[name] = pose
            received = True
        if received:
            self._actual_pose_received_s = self.get_clock().now().nanoseconds * 1.0e-9

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
                    cyclic=bool(actor.get("cyclic_goals", True)),
                    robot_avoidance_distance_m=float(actor.get("robot_avoidance_distance_m", 1.3)),
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
        if self._navigation_active and not self._experiment_started and self._logger_ready:
            # GoalMux remains stopped until it receives the repeatedly
            # published start signal, regardless of DDS discovery order.
            self._experiment_started = True
            self._route_elapsed = {route.name: 0.0 for route in self._routes}
            self._last_update_s = now
            self.get_logger().info("episode handshake complete; released actor routes")
        if self._last_update_s is None:
            self._last_update_s = now
        step_s = max(0.0, now - self._last_update_s) if self._experiment_started else 0.0
        self._last_update_s = now
        pose_array = PoseArray()
        pose_array.header.stamp = self.get_clock().now().to_msg()
        pose_array.header.frame_id = "map"
        for route in self._routes:
            proxy_name = self._proxy_name(route.name)
            current = route.pose_at(self._route_elapsed[route.name])

            def make_pose(state: tuple[float, float, float]) -> Pose:
                actor_pose = Pose()
                actor_pose.position.x = state[0]
                actor_pose.position.y = state[1]
                actor_pose.orientation = _quaternion(state[2])
                return actor_pose

            current_pose = make_pose(current)
            if proxy_name not in self._spawn_attempted:
                request = SpawnEntity.Request()
                request.entity_factory.name = proxy_name
                request.entity_factory.allow_renaming = False
                request.entity_factory.sdf = self._proxy_sdf(proxy_name)
                request.entity_factory.pose = current_pose
                request.entity_factory.relative_to = "world"
                self._spawn_pending[proxy_name] = self._spawn_client.call_async(request)
                self._spawn_attempted.add(proxy_name)
                pose_array.poses.append(current_pose)
                continue
            spawn_pending = self._spawn_pending.get(proxy_name)
            if spawn_pending is not None and not spawn_pending.done():
                pose_array.poses.append(current_pose)
                continue
            if proxy_name not in self._spawn_validated:
                response = spawn_pending.result() if spawn_pending is not None else None
                if response is None or not bool(getattr(response, "success", False)):
                    detail = getattr(response, "status_message", "no spawn response")
                    self._healthy = False
                    self.get_logger().error(f"failed to spawn LiDAR proxy {proxy_name}: {detail}")
                    pose_array.poses.append(current_pose)
                    continue
                self._spawn_validated.add(proxy_name)
                self.get_logger().info(f"spawned LiDAR-visible proxy {proxy_name}")

            # Commit route time and publish privileged truth only after Gazebo
            # confirms the corresponding proxy pose. Publishing the requested
            # pose here would lead LiDAR geometry by one 2 Hz actor step.
            pending = self._pending.get(proxy_name)
            if pending is not None and not pending.done():
                pending_since = self._pending_since_s.get(proxy_name, now)
                timeout_s = float(self.get_parameter("pose_update_timeout_s").value)
                if now - pending_since > timeout_s:
                    self._healthy = False
                    self.get_logger().error(
                        f"pose update timed out for {proxy_name}",
                        throttle_duration_sec=5.0,
                    )
                pose_array.poses.append(current_pose)
                continue
            if pending is not None:
                try:
                    response = pending.result()
                except Exception as error:  # pragma: no cover - ROS future boundary
                    self._healthy = False
                    self.get_logger().error(f"pose update failed for {proxy_name}: {error}")
                    pose_array.poses.append(current_pose)
                    continue
                if response is None or not bool(response.success):
                    self._healthy = False
                    self.get_logger().error(f"pose update rejected for {proxy_name}")
                    pose_array.poses.append(current_pose)
                    continue
                self._route_elapsed[route.name] = self._pending_target_elapsed.pop(
                    proxy_name, self._route_elapsed[route.name]
                )
                self._pending.pop(proxy_name, None)
                self._pending_since_s.pop(proxy_name, None)
                current = route.pose_at(self._route_elapsed[route.name])
                current_pose = make_pose(current)

            candidate_elapsed = self._route_elapsed[route.name] + step_s
            candidate = route.pose_at(candidate_elapsed)
            blocked_by_robot = (
                self._robot_position is not None
                and math.dist(candidate[:2], self._robot_position)
                < route.robot_avoidance_distance_m
            )
            target_elapsed = (
                self._route_elapsed[route.name] if blocked_by_robot else candidate_elapsed
            )
            x, y, yaw = route.pose_at(target_elapsed)
            target_pose = make_pose((x, y, yaw))
            pose_array.poses.append(current_pose)

            request = SetEntityPose.Request()
            request.entity.name = proxy_name
            request.entity.type = Entity.MODEL
            request.pose = target_pose
            self._pending[proxy_name] = self._client.call_async(request)
            self._pending_since_s[proxy_name] = now
            self._pending_target_elapsed[proxy_name] = target_elapsed

            if bool(self.get_parameter("update_native_actors").value):
                entity_name = route.name
                native_pending = self._pending.get(entity_name)
                if native_pending is not None and not native_pending.done():
                    continue
                if native_pending is not None:
                    try:
                        response = native_pending.result()
                    except Exception as error:  # pragma: no cover - ROS future boundary
                        self._healthy = False
                        self.get_logger().error(f"pose update failed for {entity_name}: {error}")
                        continue
                    if response is None or not bool(response.success):
                        self._healthy = False
                        self.get_logger().error(f"pose update rejected for {entity_name}")
                        continue
                request = SetEntityPose.Request()
                request.entity.name = entity_name
                request.entity.type = Entity.MODEL
                request.pose = target_pose
                self._pending[entity_name] = self._client.call_async(request)
                self._pending_since_s[entity_name] = now
        expected_proxy_names = tuple(self._proxy_name(route.name) for route in self._routes)
        actual_ready = self._actual_robot_pose is not None and all(
            name in self._actual_proxy_poses for name in expected_proxy_names
        )
        actual_fresh = (
            self._actual_pose_received_s is not None
            and now - self._actual_pose_received_s
            <= float(self.get_parameter("actual_pose_timeout_s").value)
        )
        if actual_ready and actual_fresh:
            pose_array.poses = [self._actual_proxy_poses[name] for name in expected_proxy_names]
            self._publisher.publish(pose_array)
            robot_pose = PoseStamped()
            robot_pose.header = pose_array.header
            robot_pose.pose = self._actual_robot_pose
            self._robot_pose_publisher.publish(robot_pose)
            self._actual_pose_wait_since_s = None
        elif len(self._spawn_validated) == len(expected_proxy_names):
            if self._actual_pose_wait_since_s is None:
                self._actual_pose_wait_since_s = now
            elif now - self._actual_pose_wait_since_s > float(
                self.get_parameter("actual_pose_timeout_s").value
            ):
                self._healthy = False
                self.get_logger().error(
                    "Gazebo actual pedestrian poses are missing or stale",
                    throttle_duration_sec=5.0,
                )
        health = Bool()
        health.data = self._healthy
        self._health_publisher.publish(health)
        started = Bool()
        started.data = self._experiment_started
        self._start_publisher.publish(started)


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
