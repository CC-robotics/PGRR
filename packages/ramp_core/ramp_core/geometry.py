"""Two-dimensional geometry with explicit frame transforms."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from itertools import pairwise

from ramp_core.types import Pose2D

OrientedBox2D = tuple[float, float, float, float, float]


def normalize_angle(angle: float) -> float:
    """Map an angle to the half-open interval [-pi, pi)."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def distance(first: Pose2D, second: Pose2D) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


def robot_to_world(point: tuple[float, float], robot: Pose2D) -> tuple[float, float]:
    cosine = math.cos(robot.yaw)
    sine = math.sin(robot.yaw)
    x, y = point
    return robot.x + cosine * x - sine * y, robot.y + sine * x + cosine * y


def world_to_robot(point: tuple[float, float], robot: Pose2D) -> tuple[float, float]:
    dx = point[0] - robot.x
    dy = point[1] - robot.y
    cosine = math.cos(robot.yaw)
    sine = math.sin(robot.yaw)
    return cosine * dx + sine * dy, -sine * dx + cosine * dy


def point_to_oriented_box_distance(
    point: tuple[float, float],
    center: tuple[float, float],
    half_extents: tuple[float, float],
    yaw: float = 0.0,
) -> float:
    """Return Euclidean surface distance to a filled 2-D oriented box."""
    values = (*point, *center, *half_extents, yaw)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("box geometry must be finite")
    if half_extents[0] < 0.0 or half_extents[1] < 0.0:
        raise ValueError("box half extents must be non-negative")
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    local_x = cosine * dx + sine * dy
    local_y = -sine * dx + cosine * dy
    outside_x = max(abs(local_x) - half_extents[0], 0.0)
    outside_y = max(abs(local_y) - half_extents[1], 0.0)
    return math.hypot(outside_x, outside_y)


def parse_shelf_boxes(payload: str) -> tuple[OrientedBox2D, ...]:
    """Parse Arena shelf poses into the exact 2-D collision boxes used at runtime."""
    obstacles = json.loads(payload)
    if not isinstance(obstacles, list):
        raise ValueError("static_obstacles_json must contain a list")
    boxes: list[OrientedBox2D] = []
    for obstacle in obstacles:
        if not isinstance(obstacle, dict) or obstacle.get("model") != "shelf":
            raise ValueError("physical static geometry currently supports only shelf models")
        position = obstacle.get("pos")
        if not isinstance(position, list) or len(position) < 2:
            raise ValueError("static shelf requires a position")
        yaw = float(position[2]) if len(position) > 2 else 0.0
        # shelf_static.sdf spans x +/-0.45 and local y [-0.395, 0.005].
        center_x = float(position[0]) + 0.195 * math.sin(yaw)
        center_y = float(position[1]) - 0.195 * math.cos(yaw)
        boxes.append((center_x, center_y, 0.45, 0.20, yaw))
    return tuple(boxes)


def point_to_polyline_distance(
    point: tuple[float, float],
    polyline: Sequence[tuple[float, float]],
) -> float:
    if not polyline:
        return math.inf
    if len(polyline) == 1:
        return math.dist(point, polyline[0])
    best = math.inf
    px, py = point
    for start, end in pairwise(polyline):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared == 0.0:
            candidate = math.dist(point, start)
        else:
            fraction = max(
                0.0, min(1.0, ((px - start[0]) * dx + (py - start[1]) * dy) / length_squared)
            )
            candidate = math.hypot(px - (start[0] + fraction * dx), py - (start[1] + fraction * dy))
        best = min(best, candidate)
    return best
