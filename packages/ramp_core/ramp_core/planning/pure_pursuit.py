"""Compact pure-pursuit tracker for expert rollouts."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ramp_core.geometry import normalize_angle
from ramp_core.types import Pose2D, Velocity2D


def pure_pursuit_command(
    pose: Pose2D,
    path: Sequence[tuple[float, float]],
    *,
    lookahead: float = 0.5,
    target_speed: float = 0.45,
    max_angular_speed: float = 1.2,
) -> Velocity2D:
    if lookahead <= 0.0 or target_speed < 0.0 or max_angular_speed <= 0.0:
        raise ValueError("invalid pure-pursuit limits")
    if not path:
        return Velocity2D(0.0, 0.0)
    target = path[-1]
    for point in path:
        if math.hypot(point[0] - pose.x, point[1] - pose.y) >= lookahead:
            target = point
            break
    heading = math.atan2(target[1] - pose.y, target[0] - pose.x)
    alpha = normalize_angle(heading - pose.yaw)
    curvature = 2.0 * math.sin(alpha) / lookahead
    angular = max(-max_angular_speed, min(max_angular_speed, target_speed * curvature))
    linear = target_speed * max(0.0, math.cos(alpha))
    return Velocity2D(linear, angular)
