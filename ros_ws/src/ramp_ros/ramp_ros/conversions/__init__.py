"""Explicit ROS/core value conversions."""

from __future__ import annotations

import math

from geometry_msgs.msg import Pose
from ramp_core.types import Pose2D


def pose2d_from_ros(message: Pose) -> Pose2D:
    sin_yaw = 2.0 * (message.orientation.w * message.orientation.z)
    cos_yaw = 1.0 - 2.0 * (message.orientation.z * message.orientation.z)
    return Pose2D(message.position.x, message.position.y, math.atan2(sin_yaw, cos_yaw))
