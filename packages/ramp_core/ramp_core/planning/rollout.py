"""Deterministic differential-drive rollouts with privileged human prediction."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ramp_core.action_space import RecoveryAction, RecoveryActionKind
from ramp_core.geometry import point_to_polyline_distance
from ramp_core.kinematics import integrate_differential_drive
from ramp_core.observations import PrivilegedState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.astar import astar
from ramp_core.planning.pure_pursuit import pure_pursuit_command
from ramp_core.types import Pose2D, Velocity2D


@dataclass(frozen=True, slots=True)
class CollisionGuardedHumanStep:
    """Deterministic result of one collision-guarded pedestrian step.

    ``progress_fraction`` is measured along the proposed human segment.  It is
    therefore also usable by waypoint controllers whose route clock advances
    linearly over one update.  The soft-hold clock is explicit so callers can
    commit it only after a simulator pose transaction succeeds.
    """

    position: tuple[float, float]
    progress_fraction: float
    soft_hold_elapsed_s: float
    swept_clearance_m: float
    reason: str
    guard_intervened: bool
    soft_yielded: bool


def _finite_point(name: str, point: tuple[float, float]) -> None:
    if len(point) != 2 or any(not math.isfinite(value) for value in point):
        raise ValueError(f"{name} must contain two finite coordinates")


def same_time_swept_clearance(
    robot_start: tuple[float, float],
    robot_end: tuple[float, float],
    human_start: tuple[float, float],
    human_end: tuple[float, float],
) -> float:
    """Return minimum separation for two linearly moving centres.

    The two segments are synchronized over the same normalized time interval;
    this is intentionally different from the unconstrained distance between
    two geometric segments.  The calculation is the closest point of the
    relative-motion segment to the origin.
    """

    for name, point in (
        ("robot_start", robot_start),
        ("robot_end", robot_end),
        ("human_start", human_start),
        ("human_end", human_end),
    ):
        _finite_point(name, point)
    relative_start = (
        human_start[0] - robot_start[0],
        human_start[1] - robot_start[1],
    )
    relative_delta = (
        (human_end[0] - human_start[0]) - (robot_end[0] - robot_start[0]),
        (human_end[1] - human_start[1]) - (robot_end[1] - robot_start[1]),
    )
    speed_squared = relative_delta[0] ** 2 + relative_delta[1] ** 2
    if speed_squared <= 1.0e-18:
        return math.hypot(*relative_start)
    closest_time = (
        -(relative_start[0] * relative_delta[0] + relative_start[1] * relative_delta[1])
        / speed_squared
    )
    closest_time = min(1.0, max(0.0, closest_time))
    return math.hypot(
        relative_start[0] + closest_time * relative_delta[0],
        relative_start[1] + closest_time * relative_delta[1],
    )


def collision_guarded_human_step(
    robot_position: tuple[float, float],
    robot_velocity: tuple[float, float],
    current_position: tuple[float, float],
    candidate_position: tuple[float, float],
    step_duration_s: float,
    *,
    soft_yield_distance_m: float = 0.90,
    hard_collision_guard_m: float = 0.73,
    maximum_soft_hold_s: float = 1.0,
    soft_hold_elapsed_s: float = 0.0,
) -> CollisionGuardedHumanStep:
    """Apply bounded yielding plus a continuous swept collision guard.

    A guard-safe pedestrian is never held indefinitely just because it enters
    the wider social-yield zone.  Approaching motion may make one bounded soft
    hold, after which it proceeds while it remains hard-guard safe.  If the
    proposed step violates the hard guard, the connected safe prefix is used;
    when no forward prefix is safe, the pedestrian holds.  A robot that has
    already entered the guard cannot freeze a pedestrian that is moving
    monotonically away, but no cross-through trajectory is accepted merely
    because its endpoint is farther away.
    """

    for name, point in (
        ("robot_position", robot_position),
        ("robot_velocity", robot_velocity),
        ("current_position", current_position),
        ("candidate_position", candidate_position),
    ):
        _finite_point(name, point)
    scalars = (
        step_duration_s,
        soft_yield_distance_m,
        hard_collision_guard_m,
        maximum_soft_hold_s,
        soft_hold_elapsed_s,
    )
    if any(not math.isfinite(value) for value in scalars):
        raise ValueError("collision-guard parameters must be finite")
    if step_duration_s <= 0.0:
        raise ValueError("step_duration_s must be positive")
    if hard_collision_guard_m <= 0.0:
        raise ValueError("hard_collision_guard_m must be positive")
    if soft_yield_distance_m <= hard_collision_guard_m:
        raise ValueError("soft_yield_distance_m must exceed hard_collision_guard_m")
    if maximum_soft_hold_s < 0.0 or soft_hold_elapsed_s < 0.0:
        raise ValueError("soft-hold durations must be non-negative")

    robot_end = (
        robot_position[0] + robot_velocity[0] * step_duration_s,
        robot_position[1] + robot_velocity[1] * step_duration_s,
    )
    current_clearance = math.dist(robot_position, current_position)
    endpoint_clearance = math.dist(robot_end, candidate_position)
    full_clearance = same_time_swept_clearance(
        robot_position,
        robot_end,
        current_position,
        candidate_position,
    )
    relative_start = (
        current_position[0] - robot_position[0],
        current_position[1] - robot_position[1],
    )
    relative_delta = (
        (candidate_position[0] - current_position[0]) - (robot_end[0] - robot_position[0]),
        (candidate_position[1] - current_position[1]) - (robot_end[1] - robot_position[1]),
    )
    initial_clearance_derivative = (
        relative_start[0] * relative_delta[0] + relative_start[1] * relative_delta[1]
    )
    tolerance = 1.0e-9

    def result(
        position: tuple[float, float],
        fraction: float,
        hold_elapsed: float,
        clearance: float,
        reason: str,
        *,
        intervened: bool,
        soft_yielded: bool = False,
    ) -> CollisionGuardedHumanStep:
        return CollisionGuardedHumanStep(
            position=position,
            progress_fraction=fraction,
            soft_hold_elapsed_s=hold_elapsed,
            swept_clearance_m=clearance,
            reason=reason,
            guard_intervened=intervened,
            soft_yielded=soft_yielded,
        )

    # When the robot has already entered the guard, an endpoint farther away
    # is insufficient: the relative trajectory must increase clearance from
    # the first instant, which rules out a through-robot chord.
    if current_clearance < hard_collision_guard_m - tolerance:
        strictly_escaping = bool(
            endpoint_clearance > current_clearance + tolerance
            and initial_clearance_derivative > tolerance
            and full_clearance >= current_clearance - tolerance
        )
        if strictly_escaping:
            return result(
                candidate_position,
                1.0,
                0.0,
                full_clearance,
                "inside_guard_escape",
                intervened=False,
            )
        hold_clearance = same_time_swept_clearance(
            robot_position,
            robot_end,
            current_position,
            current_position,
        )
        return result(
            current_position,
            0.0,
            0.0,
            hold_clearance,
            "inside_guard_non_escaping_hold",
            intervened=True,
        )

    if full_clearance >= hard_collision_guard_m - tolerance:
        approaching = endpoint_clearance < current_clearance - tolerance
        inside_soft_zone = full_clearance < soft_yield_distance_m
        hold_fits_budget = soft_hold_elapsed_s + step_duration_s <= maximum_soft_hold_s + tolerance
        if approaching and inside_soft_zone and hold_fits_budget:
            hold_clearance = same_time_swept_clearance(
                robot_position,
                robot_end,
                current_position,
                current_position,
            )
            # Do not make a polite hold when the robot's predicted motion makes
            # holding less safe than the already guard-safe pedestrian step.
            if hold_clearance >= hard_collision_guard_m - tolerance:
                elapsed = min(
                    maximum_soft_hold_s,
                    soft_hold_elapsed_s + step_duration_s,
                )
                return result(
                    current_position,
                    0.0,
                    elapsed,
                    hold_clearance,
                    "soft_yield_hold",
                    intervened=False,
                    soft_yielded=True,
                )
        hold_elapsed = (
            maximum_soft_hold_s
            if approaching and inside_soft_zone and maximum_soft_hold_s > 0.0
            else 0.0
        )
        reason = (
            "soft_yield_budget_exhausted"
            if approaching and inside_soft_zone and not hold_fits_budget
            else "guard_safe_motion"
        )
        return result(
            candidate_position,
            1.0,
            hold_elapsed,
            full_clearance,
            reason,
            intervened=False,
        )

    hold_clearance = same_time_swept_clearance(
        robot_position,
        robot_end,
        current_position,
        current_position,
    )
    if hold_clearance < hard_collision_guard_m - tolerance:
        # No route-forward action connected to a stationary hold can make the
        # robot's predicted incursion safe. The actor contributes no motion;
        # the robot-side safety supervisor remains authoritative.
        return result(
            current_position,
            0.0,
            0.0,
            hold_clearance,
            "guard_no_safe_forward_step",
            intervened=True,
        )

    human_delta = (
        candidate_position[0] - current_position[0],
        candidate_position[1] - current_position[1],
    )

    def clearance_for_fraction(fraction: float) -> float:
        endpoint = (
            current_position[0] + fraction * human_delta[0],
            current_position[1] + fraction * human_delta[1],
        )
        return same_time_swept_clearance(
            robot_position,
            robot_end,
            current_position,
            endpoint,
        )

    # Find the first unsafe speed interval connected to the safe hold at zero,
    # then refine its boundary. Ignoring disconnected high-speed safe islands
    # is conservative and prevents a pedestrian from jumping through a guard.
    safe_fraction = 0.0
    unsafe_fraction = 1.0
    subdivisions = 128
    for index in range(1, subdivisions + 1):
        fraction = index / subdivisions
        if clearance_for_fraction(fraction) < hard_collision_guard_m:
            unsafe_fraction = fraction
            break
        safe_fraction = fraction
    for _ in range(48):
        midpoint = (safe_fraction + unsafe_fraction) / 2.0
        if clearance_for_fraction(midpoint) >= hard_collision_guard_m:
            safe_fraction = midpoint
        else:
            unsafe_fraction = midpoint
    # Step a tiny distance back from the numerical boundary and verify the
    # postcondition before exposing the truncated target to a simulator.
    safe_fraction = max(0.0, safe_fraction - 1.0e-9)
    truncated = (
        current_position[0] + safe_fraction * human_delta[0],
        current_position[1] + safe_fraction * human_delta[1],
    )
    truncated_clearance = clearance_for_fraction(safe_fraction)
    if safe_fraction <= 1.0e-8 or truncated_clearance < hard_collision_guard_m - tolerance:
        return result(
            current_position,
            0.0,
            0.0,
            hold_clearance,
            "hard_guard_hold",
            intervened=True,
        )
    return result(
        truncated,
        safe_fraction,
        0.0,
        truncated_clearance,
        "hard_guard_truncated",
        intervened=True,
    )


def yielding_human_step(
    robot_position: tuple[float, float],
    current_position: tuple[float, float],
    candidate_position: tuple[float, float],
    avoidance_distance_m: float,
) -> tuple[float, float]:
    """Hold a human only when its candidate step fails to increase robot clearance.

    A person already inside the avoidance radius must remain able to walk away.
    Freezing every candidate inside the radius creates a reciprocal deadlock in
    which neither the robot nor the yielding person can restore clearance.
    """

    if avoidance_distance_m < 0.0 or not math.isfinite(avoidance_distance_m):
        raise ValueError("avoidance_distance_m must be finite and non-negative")
    values = (*robot_position, *current_position, *candidate_position)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("yielding positions must be finite")
    current_distance = math.dist(robot_position, current_position)
    candidate_distance = math.dist(robot_position, candidate_position)
    blocked = (
        avoidance_distance_m > 0.0
        and candidate_distance < avoidance_distance_m
        and candidate_distance <= current_distance
    )
    return current_position if blocked else candidate_position


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
    human_yield_distance_m: float = 1.3

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
        if self.prediction_inflation_mps < 0.0 or self.human_yield_distance_m < 0.0:
            raise ValueError("prediction inflation and human yield distance must be non-negative")


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
    human_positions = [human.position for human in state.humans]
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
        for human_index, human in enumerate(state.humans):
            current_human = human_positions[human_index]
            candidate_human = (
                current_human[0] + human.velocity[0] * cfg.dt_s,
                current_human[1] + human.velocity[1] * cfg.dt_s,
            )
            predicted = (
                current_human
                if cfg.human_yield_distance_m > 0.0
                and math.dist((pose.x, pose.y), candidate_human) < cfg.human_yield_distance_m
                else candidate_human
            )
            human_positions[human_index] = predicted
            # Constant velocity alone is optimistic when a person brakes or
            # yields. Treat every point from the current position to the CV
            # prediction as reachable during this step, then inflate that
            # swept tube with time. Unlike the online fallback, the expert
            # intentionally does not assume that a receding person must keep
            # moving; set the yielding distance to zero for a pure
            # constant-velocity environment.
            distance = point_to_polyline_distance(
                (pose.x, pose.y),
                (current_human, predicted),
            )
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
