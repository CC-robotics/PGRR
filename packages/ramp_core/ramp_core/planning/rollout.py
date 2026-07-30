"""Deterministic differential-drive rollouts with privileged human prediction."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ramp_core.action_space import RecoveryAction, RecoveryActionKind
from ramp_core.kinematics import integrate_differential_drive
from ramp_core.observations import PrivilegedState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.astar import astar
from ramp_core.planning.pure_pursuit import pure_pursuit_command
from ramp_core.types import Pose2D, Velocity2D


@dataclass(frozen=True, slots=True)
class RolloutConfig:
    horizon_s: float = 3.0
    dt_s: float = 0.1
    target_speed_mps: float = 0.35
    backup_speed_mps: float = 0.15
    backup_duration_s: float = 1.0
    lookahead_m: float = 0.4
    max_angular_speed_radps: float = 1.0
    robot_radius_m: float = 0.36
    prediction_inflation_mps: float = 0.03

    def __post_init__(self) -> None:
        positive = (
            self.horizon_s,
            self.dt_s,
            self.target_speed_mps,
            self.backup_speed_mps,
            self.backup_duration_s,
            self.lookahead_m,
            self.max_angular_speed_radps,
            self.robot_radius_m,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("rollout durations, speeds, and radii must be positive")
        if self.prediction_inflation_mps < 0.0:
            raise ValueError("prediction_inflation_mps must be non-negative")


@dataclass(frozen=True, slots=True)
class RolloutResult:
    poses: tuple[Pose2D, ...]
    commands: tuple[Velocity2D, ...]
    collision: bool
    minimum_human_distance_m: float
    social_violation_integral: float
    goal_progress_m: float
    rejoin_distance_m: float
    path_length_m: float
    angular_smoothness: float


def _nearest_path_suffix(
    path: tuple[tuple[float, float], ...], pose: Pose2D
) -> tuple[tuple[float, float], ...]:
    if not path:
        return ()
    nearest = min(
        range(len(path)),
        key=lambda index: math.dist((pose.x, pose.y), path[index]),
    )
    return path[nearest:]


def _grid_path(
    grid: OccupancyGrid,
    start: tuple[float, float],
    goal: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    indices = astar(grid, grid.world_to_grid(*start), grid.world_to_grid(*goal))
    return tuple(grid.grid_to_world(index) for index in indices)


def rollout_action(
    state: PrivilegedState,
    action: RecoveryAction,
    grid: OccupancyGrid,
    *,
    config: RolloutConfig | None = None,
    personal_space_m: float = 1.0,
) -> RolloutResult:
    cfg = config if config is not None else RolloutConfig()
    if personal_space_m < 0.0:
        raise ValueError("personal_space_m must be non-negative")
    pose = state.robot_pose
    start_goal_distance = math.dist(
        (pose.x, pose.y), (state.original_goal.x, state.original_goal.y)
    )
    target_path: tuple[tuple[float, float], ...] = ()
    if action.kind is RecoveryActionKind.SUBGOAL:
        target = action.target_pose(pose)
        assert target is not None
        target_path = _grid_path(grid, (pose.x, pose.y), (target.x, target.y))
    elif action.kind in {RecoveryActionKind.CONTINUE, RecoveryActionKind.REPLAN}:
        if action.kind is RecoveryActionKind.REPLAN:
            target_path = _grid_path(
                grid,
                (pose.x, pose.y),
                (state.original_goal.x, state.original_goal.y),
            )
        else:
            target_path = _nearest_path_suffix(state.global_path, pose)

    poses = [pose]
    commands: list[Velocity2D] = []
    collision = False
    minimum_human_distance = math.inf
    social_integral = 0.0
    path_length = 0.0
    angular_smoothness = 0.0
    previous_angular = state.robot_velocity.angular
    steps = max(1, math.ceil(cfg.horizon_s / cfg.dt_s))
    for step in range(steps):
        elapsed = step * cfg.dt_s
        if action.kind is RecoveryActionKind.WAIT:
            command = Velocity2D(0.0, 0.0)
        elif action.kind is RecoveryActionKind.BACKUP:
            command = (
                Velocity2D(-cfg.backup_speed_mps, 0.0)
                if elapsed < cfg.backup_duration_s
                else Velocity2D(0.0, 0.0)
            )
        elif target_path and math.dist((pose.x, pose.y), target_path[-1]) > 0.10:
            command = pure_pursuit_command(
                pose,
                target_path,
                lookahead=cfg.lookahead_m,
                target_speed=cfg.target_speed_mps,
                max_angular_speed=cfg.max_angular_speed_radps,
            )
        else:
            command = Velocity2D(0.0, 0.0)
        next_pose = integrate_differential_drive(pose, command, cfg.dt_s)
        if not grid.is_free(grid.world_to_grid(next_pose.x, next_pose.y)):
            collision = True
        path_length += math.dist((pose.x, pose.y), (next_pose.x, next_pose.y))
        angular_smoothness += abs(command.angular - previous_angular)
        previous_angular = command.angular
        pose = next_pose
        poses.append(pose)
        commands.append(command)
        prediction_time = (step + 1) * cfg.dt_s
        for human in state.humans:
            predicted = (
                human.position[0] + human.velocity[0] * prediction_time,
                human.position[1] + human.velocity[1] * prediction_time,
            )
            distance = math.dist((pose.x, pose.y), predicted)
            minimum_human_distance = min(minimum_human_distance, distance)
            inflated_collision_radius = (
                cfg.robot_radius_m + human.radius + cfg.prediction_inflation_mps * prediction_time
            )
            collision |= distance <= inflated_collision_radius
            social_integral += max(0.0, personal_space_m - distance) * cfg.dt_s

    final_goal_distance = math.dist(
        (pose.x, pose.y), (state.original_goal.x, state.original_goal.y)
    )
    rejoin_distance = (
        min(math.dist((pose.x, pose.y), point) for point in state.global_path)
        if state.global_path
        else final_goal_distance
    )
    return RolloutResult(
        poses=tuple(poses),
        commands=tuple(commands),
        collision=collision,
        minimum_human_distance_m=minimum_human_distance,
        social_violation_integral=social_integral,
        goal_progress_m=start_goal_distance - final_goal_distance,
        rejoin_distance_m=rejoin_distance,
        path_length_m=path_length,
        angular_smoothness=angular_smoothness,
    )
