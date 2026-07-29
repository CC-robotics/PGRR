"""Two-dimensional geometry with explicit frame transforms."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

from ramp_core.types import Pose2D


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
