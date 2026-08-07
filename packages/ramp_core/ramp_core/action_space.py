"""Fixed, documented 25-action recovery space."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ramp_core.geometry import robot_to_world
from ramp_core.types import Pose2D

RADII_METERS = (0.6, 1.0, 1.4)
ANGLES_DEGREES = (-90, -60, -30, 0, 30, 60, 90)
WAIT_ACTION_ID = 21
BACKUP_ACTION_ID = 22
REPLAN_ACTION_ID = 23
CONTINUE_ACTION_ID = 24
ACTION_COUNT = 25


class RecoveryActionKind(str, Enum):
    SUBGOAL = "SUBGOAL"
    WAIT = "WAIT"
    BACKUP = "BACKUP"
    REPLAN = "REPLAN"
    CONTINUE = "CONTINUE"


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action_id: int
    kind: RecoveryActionKind
    radius: float | None = None
    angle_degrees: int | None = None

    def target_pose(self, robot: Pose2D) -> Pose2D | None:
        if self.kind is not RecoveryActionKind.SUBGOAL:
            return None
        assert self.radius is not None and self.angle_degrees is not None
        angle = math.radians(self.angle_degrees)
        point = robot_to_world(
            (self.radius * math.cos(angle), self.radius * math.sin(angle)), robot
        )
        return Pose2D(point[0], point[1], robot.yaw + angle)


def build_action_space() -> tuple[RecoveryAction, ...]:
    actions: list[RecoveryAction] = []
    for radius in RADII_METERS:
        for angle in ANGLES_DEGREES:
            actions.append(
                RecoveryAction(
                    action_id=len(actions),
                    kind=RecoveryActionKind.SUBGOAL,
                    radius=radius,
                    angle_degrees=angle,
                )
            )
    actions.extend(
        [
            RecoveryAction(WAIT_ACTION_ID, RecoveryActionKind.WAIT),
            RecoveryAction(BACKUP_ACTION_ID, RecoveryActionKind.BACKUP),
            RecoveryAction(REPLAN_ACTION_ID, RecoveryActionKind.REPLAN),
            RecoveryAction(CONTINUE_ACTION_ID, RecoveryActionKind.CONTINUE),
        ]
    )
    if [action.action_id for action in actions] != list(range(ACTION_COUNT)):
        raise RuntimeError("recovery action IDs are not contiguous")
    return tuple(actions)


ACTIONS = build_action_space()


def action_by_id(action_id: int) -> RecoveryAction:
    if not 0 <= action_id < ACTION_COUNT:
        raise ValueError(f"action_id must be in [0, {ACTION_COUNT - 1}]")
    return ACTIONS[action_id]
