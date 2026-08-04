"""Deterministic Gazebo actor motion fallback for Arena Humble scenarios."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Pose, PoseArray, PoseStamped, Quaternion
from nav2_msgs.srv import ClearEntireCostmap
from nav_msgs.msg import Odometry
from ramp_core.evaluation.navigation import navigation_status_is_active
from ramp_core.planning.rollout import yielding_human_step
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
        self.declare_parameter(
            "local_costmap_clear_service",
            "/local_costmap/clear_entirely_local_costmap",
        )
        self.declare_parameter(
            "global_costmap_clear_service",
            "/global_costmap/clear_entirely_global_costmap",
        )
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
        self.declare_parameter("robot_reset_position_tolerance_m", 0.10)
        self.declare_parameter("robot_reset_yaw_tolerance_rad", 0.15)
        self.declare_parameter("robot_reset_retry_interval_s", 0.50)
        self.declare_parameter("robot_reset_request_timeout_s", 2.0)
        self.declare_parameter("robot_reset_settle_s", 0.50)
        self.declare_parameter("costmap_clear_timeout_s", 5.0)
        self.declare_parameter("startup_gate_timeout_s", 45.0)
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
        local_clear_service = str(self.get_parameter("local_costmap_clear_service").value)
        global_clear_service = str(self.get_parameter("global_costmap_clear_service").value)
        self._costmap_clear_clients = {
            "local": self.create_client(ClearEntireCostmap, local_clear_service),
            "global": self.create_client(ClearEntireCostmap, global_clear_service),
        }
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
        self._robot_start = (
            float(self.get_parameter("robot_start_x").value),
            float(self.get_parameter("robot_start_y").value),
            float(self.get_parameter("robot_start_yaw").value),
        )
        if not all(math.isfinite(value) for value in self._robot_start):
            raise ValueError("robot start pose must be finite")
        positive_parameters = (
            "actual_pose_timeout_s",
            "pose_update_timeout_s",
            "robot_reset_position_tolerance_m",
            "robot_reset_yaw_tolerance_rad",
            "robot_reset_retry_interval_s",
            "robot_reset_request_timeout_s",
            "costmap_clear_timeout_s",
            "startup_gate_timeout_s",
        )
        for parameter_name in positive_parameters:
            value = float(self.get_parameter(parameter_name).value)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{parameter_name} must be positive")
        reset_settle_s = float(self.get_parameter("robot_reset_settle_s").value)
        if not math.isfinite(reset_settle_s) or reset_settle_s < 0.0:
            raise ValueError("robot_reset_settle_s must be finite and non-negative")
        yaw_tolerance = float(self.get_parameter("robot_reset_yaw_tolerance_rad").value)
        if not math.isfinite(yaw_tolerance) or yaw_tolerance > math.pi:
            raise ValueError("robot_reset_yaw_tolerance_rad must be finite and at most pi")
        for parameter_name, service in (
            ("set_pose_service", service_name),
            ("spawn_service", spawn_service),
            ("local_costmap_clear_service", local_clear_service),
            ("global_costmap_clear_service", global_clear_service),
        ):
            if not service.strip():
                raise ValueError(f"{parameter_name} must not be empty")
        self._robot_position: tuple[float, float] | None = None
        self._last_update_s: float | None = None
        self._wait_for_navigation_active = bool(
            self.get_parameter("wait_for_navigation_active").value
        )
        self._navigation_active = not self._wait_for_navigation_active
        self._experiment_started = not self._wait_for_navigation_active
        self._logger_ready = not self._wait_for_navigation_active
        self._startup_gate_ready = not self._wait_for_navigation_active
        self._startup_gate_failed = False
        self._startup_gate_started_wall_s = time.monotonic()
        self._robot_at_start_since_wall_s: float | None = None
        self._robot_reset_pending: Any | None = None
        self._robot_reset_pending_since_wall_s: float | None = None
        self._robot_reset_last_attempt_wall_s: float | None = None
        self._robot_reset_attempts = 0
        self._costmap_clear_pending: dict[str, Any] = {}
        self._costmap_clear_started_wall_s: float | None = None
        self._route_elapsed = {route.name: 0.0 for route in self._routes}
        self._pending: dict[str, Any] = {}
        self._pending_since_s: dict[str, float] = {}
        self._pending_target_elapsed: dict[str, float] = {}
        self._spawn_pending: dict[str, Any] = {}
        self._spawn_attempted: set[str] = set()
        self._spawn_validated: set[str] = set()
        self._actual_proxy_poses: dict[str, Pose] = {}
        self._actual_robot_pose: Pose | None = None
        self._actual_robot_pose_received_s: float | None = None
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
            f"loaded {len(self._routes)} deterministic actor routes; service={service_name}; "
            f"startup_costmaps=({local_clear_service}, {global_clear_service})"
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

    @staticmethod
    def _yaw(pose: Pose) -> float:
        q = pose.orientation
        return math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    def _robot_pose_errors(self) -> tuple[float, float] | None:
        if self._actual_robot_pose is None:
            return None
        start_x, start_y, start_yaw = self._robot_start
        actual_x = float(self._actual_robot_pose.position.x)
        actual_y = float(self._actual_robot_pose.position.y)
        actual_yaw = self._yaw(self._actual_robot_pose)
        values = (actual_x, actual_y, actual_yaw)
        if not all(math.isfinite(value) for value in values):
            return None
        yaw_error = abs(
            math.atan2(
                math.sin(actual_yaw - start_yaw),
                math.cos(actual_yaw - start_yaw),
            )
        )
        return math.hypot(actual_x - start_x, actual_y - start_y), yaw_error

    def _actual_robot_pose_is_fresh(self, now_s: float) -> bool:
        return bool(
            self._actual_robot_pose_received_s is not None
            and now_s - self._actual_robot_pose_received_s
            <= float(self.get_parameter("actual_pose_timeout_s").value)
        )

    def _robot_is_at_configured_start(self, now_s: float) -> bool:
        errors = self._robot_pose_errors()
        if errors is None or not self._actual_robot_pose_is_fresh(now_s):
            return False
        return bool(
            errors[0] <= float(self.get_parameter("robot_reset_position_tolerance_m").value)
            and errors[1] <= float(self.get_parameter("robot_reset_yaw_tolerance_rad").value)
        )

    def _fail_startup_gate(self, detail: str) -> None:
        if self._startup_gate_failed:
            return
        self._startup_gate_failed = True
        self._healthy = False
        self.get_logger().error(f"startup gate failed; actors_healthy=false: {detail}")

    def _request_robot_reset(self, now_wall_s: float) -> None:
        # This guard is the hard no-teleport invariant for active episodes.
        if self._experiment_started:
            self._fail_startup_gate("refused robot teleport after experiment_started")
            return
        if not self._client.service_is_ready():
            self.get_logger().warning(
                "startup gate waiting for Gazebo robot set_pose service",
                throttle_duration_sec=5.0,
            )
            return
        if self._actual_robot_pose is None:
            return
        request = SetEntityPose.Request()
        request.entity.name = str(self.get_parameter("actual_robot_name").value)
        request.entity.type = Entity.MODEL
        request.pose.position.x = self._robot_start[0]
        request.pose.position.y = self._robot_start[1]
        actual_z = float(self._actual_robot_pose.position.z)
        request.pose.position.z = actual_z if math.isfinite(actual_z) else 0.0
        request.pose.orientation = _quaternion(self._robot_start[2])
        self._robot_reset_pending = self._client.call_async(request)
        self._robot_reset_pending_since_wall_s = now_wall_s
        self._robot_reset_last_attempt_wall_s = now_wall_s
        self._robot_reset_attempts += 1
        errors = self._robot_pose_errors()
        error_text = "unknown pose error"
        if errors is not None:
            error_text = f"position_error={errors[0]:.3f}m yaw_error={errors[1]:.3f}rad"
        self.get_logger().warning(
            f"startup gate requested robot reset attempt={self._robot_reset_attempts} {error_text}"
        )

    def _advance_robot_reset(self, now_s: float, now_wall_s: float) -> bool:
        pending = self._robot_reset_pending
        if pending is not None:
            pending_since = self._robot_reset_pending_since_wall_s
            assert pending_since is not None
            if not pending.done():
                if now_wall_s - pending_since > float(
                    self.get_parameter("robot_reset_request_timeout_s").value
                ):
                    pending.cancel()
                    self._robot_reset_pending = None
                    self._robot_reset_pending_since_wall_s = None
                    self.get_logger().warning(
                        "startup gate robot set_pose request timed out; retrying",
                        throttle_duration_sec=2.0,
                    )
                return False
            try:
                response = pending.result()
            except Exception as error:  # pragma: no cover - ROS future boundary
                response = None
                self.get_logger().warning(f"startup gate robot set_pose request failed: {error}")
            self._robot_reset_pending = None
            self._robot_reset_pending_since_wall_s = None
            if response is None or not bool(getattr(response, "success", False)):
                self.get_logger().warning("startup gate robot set_pose request was rejected")
            else:
                self.get_logger().info(
                    "startup gate robot set_pose accepted; waiting for Gazebo pose confirmation"
                )
            return False

        if self._robot_is_at_configured_start(now_s):
            if self._robot_at_start_since_wall_s is None:
                self._robot_at_start_since_wall_s = now_wall_s
            settled_s = now_wall_s - self._robot_at_start_since_wall_s
            if settled_s >= float(self.get_parameter("robot_reset_settle_s").value):
                return True
        else:
            self._robot_at_start_since_wall_s = None

        retry_interval_s = float(self.get_parameter("robot_reset_retry_interval_s").value)
        if self._robot_reset_last_attempt_wall_s is None or (
            now_wall_s - self._robot_reset_last_attempt_wall_s >= retry_interval_s
        ):
            if self._actual_robot_pose is None or not self._actual_robot_pose_is_fresh(now_s):
                self.get_logger().warning(
                    "startup gate waiting for fresh Gazebo robot pose",
                    throttle_duration_sec=5.0,
                )
            else:
                self._request_robot_reset(now_wall_s)
        return False

    def _advance_costmap_clear(self, now_wall_s: float) -> bool:
        if not self._costmap_clear_pending:
            unavailable = [
                name
                for name, client in self._costmap_clear_clients.items()
                if not client.service_is_ready()
            ]
            if unavailable:
                self.get_logger().warning(
                    "startup gate waiting for Nav2 costmap services: " + ", ".join(unavailable),
                    throttle_duration_sec=5.0,
                )
                return False
            self._costmap_clear_pending = {
                name: client.call_async(ClearEntireCostmap.Request())
                for name, client in self._costmap_clear_clients.items()
            }
            self._costmap_clear_started_wall_s = now_wall_s
            self.get_logger().info("startup gate requested local and global costmap clears")
            return False

        assert self._costmap_clear_started_wall_s is not None
        if now_wall_s - self._costmap_clear_started_wall_s > float(
            self.get_parameter("costmap_clear_timeout_s").value
        ):
            self._fail_startup_gate("Nav2 costmap clear responses timed out")
            return False
        if not all(future.done() for future in self._costmap_clear_pending.values()):
            return False
        for name, future in self._costmap_clear_pending.items():
            try:
                response = future.result()
            except Exception as error:  # pragma: no cover - ROS future boundary
                self._fail_startup_gate(f"{name} costmap clear failed: {error}")
                return False
            if response is None:
                self._fail_startup_gate(f"{name} costmap clear returned an error response")
                return False
        self.get_logger().info("startup gate cleared local and global Nav2 costmaps")
        return True

    def _advance_startup_gate(self, now_s: float) -> bool:
        if self._startup_gate_ready:
            return True
        if self._startup_gate_failed:
            return False
        now_wall_s = time.monotonic()
        if now_wall_s - self._startup_gate_started_wall_s > float(
            self.get_parameter("startup_gate_timeout_s").value
        ):
            errors = self._robot_pose_errors()
            detail = "fresh Gazebo robot pose unavailable"
            if errors is not None:
                detail = f"robot pose error remained {errors[0]:.3f}m/{errors[1]:.3f}rad"
            self._fail_startup_gate(f"startup timeout: {detail}")
            return False
        if not self._advance_robot_reset(now_s, now_wall_s):
            return False
        if not self._advance_costmap_clear(now_wall_s):
            return False
        # Re-check after both asynchronous clear responses.  No teleport can
        # be outstanding when the episode start signal is released.
        if not self._robot_is_at_configured_start(now_s):
            self._fail_startup_gate("robot left configured start before startup release")
            return False
        self._startup_gate_ready = True
        self.get_logger().info("startup gate ready: robot reset confirmed and costmaps cleared")
        return True

    def _on_odom(self, message: Odometry) -> None:
        if self._actual_robot_pose is not None:
            self._robot_position = (
                float(self._actual_robot_pose.position.x),
                float(self._actual_robot_pose.position.y),
            )
            return
        local_x = float(message.pose.pose.position.x)
        local_y = float(message.pose.pose.position.y)
        start_x, start_y, start_yaw = self._robot_start
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
        # TaskGenerator publishes the first active goal only after it has
        # reset the scenario and constructed the robot's map/odom transforms.
        # Starting the reset gate any earlier can teleport Gazebo while Nav2
        # is still sizing its costmaps around the pre-reset staging pose.
        self._startup_gate_started_wall_s = time.monotonic()
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
                self._actual_robot_pose_received_s = self.get_clock().now().nanoseconds * 1.0e-9
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
        startup_gate_ready = self._startup_gate_ready
        if self._navigation_active and not self._experiment_started:
            startup_gate_ready = self._advance_startup_gate(now)
        if (
            self._navigation_active
            and not self._experiment_started
            and self._logger_ready
            and startup_gate_ready
        ):
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
            blocked_by_robot = False
            if self._robot_position is not None:
                permitted = yielding_human_step(
                    self._robot_position,
                    current[:2],
                    candidate[:2],
                    route.robot_avoidance_distance_m,
                )
                blocked_by_robot = permitted == current[:2]
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
