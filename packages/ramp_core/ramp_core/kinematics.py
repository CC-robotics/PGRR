"""Differential-drive integration and conservative braking checks."""

from __future__ import annotations

import math

from ramp_core.geometry import normalize_angle
from ramp_core.types import Pose2D, Velocity2D


def integrate_differential_drive(pose: Pose2D, velocity: Velocity2D, dt: float) -> Pose2D:
    if dt < 0.0:
        raise ValueError("dt must be non-negative")
    if abs(velocity.angular) < 1e-9:
        return Pose2D(
            pose.x + velocity.linear * math.cos(pose.yaw) * dt,
            pose.y + velocity.linear * math.sin(pose.yaw) * dt,
            pose.yaw,
        )
    next_yaw = pose.yaw + velocity.angular * dt
    radius = velocity.linear / velocity.angular
    return Pose2D(
        pose.x + radius * (math.sin(next_yaw) - math.sin(pose.yaw)),
        pose.y - radius * (math.cos(next_yaw) - math.cos(pose.yaw)),
        normalize_angle(next_yaw),
    )


def stopping_distance(
    speed: float, braking_acceleration: float, latency: float, margin: float
) -> float:
    if braking_acceleration <= 0.0:
        raise ValueError("braking_acceleration must be positive")
    if latency < 0.0 or margin < 0.0:
        raise ValueError("latency and margin must be non-negative")
    forward_speed = max(0.0, speed)
    return (
        forward_speed * forward_speed / (2.0 * braking_acceleration)
        + forward_speed * latency
        + margin
    )
