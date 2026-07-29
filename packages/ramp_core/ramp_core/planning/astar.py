"""Deterministic 8-connected grid A*."""

from __future__ import annotations

import heapq
import math
from itertools import count

from ramp_core.occupancy import GridIndex, OccupancyGrid


def _heuristic(first: GridIndex, second: GridIndex) -> float:
    dx = abs(first[1] - second[1])
    dy = abs(first[0] - second[0])
    return max(dx, dy) + (math.sqrt(2.0) - 1.0) * min(dx, dy)


def astar(grid: OccupancyGrid, start: GridIndex, goal: GridIndex) -> list[GridIndex]:
    if not grid.is_free(start) or not grid.is_free(goal):
        return []
    serial = count()
    frontier: list[tuple[float, int, GridIndex]] = [(0.0, next(serial), start)]
    parent: dict[GridIndex, GridIndex | None] = {start: None}
    cost = {start: 0.0}
    neighbors = (
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, math.sqrt(2.0)),
        (-1, 1, math.sqrt(2.0)),
        (1, -1, math.sqrt(2.0)),
        (1, 1, math.sqrt(2.0)),
    )
    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current == goal:
            path: list[GridIndex] = []
            cursor: GridIndex | None = current
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            return list(reversed(path))
        for dr, dc, step_cost in neighbors:
            candidate = (current[0] + dr, current[1] + dc)
            if not grid.is_free(candidate):
                continue
            if dr != 0 and dc != 0:
                if not grid.is_free((current[0] + dr, current[1])) or not grid.is_free(
                    (current[0], current[1] + dc)
                ):
                    continue
            new_cost = cost[current] + step_cost
            if new_cost < cost.get(candidate, math.inf):
                cost[candidate] = new_cost
                parent[candidate] = current
                priority = new_cost + _heuristic(candidate, goal)
                heapq.heappush(frontier, (priority, next(serial), candidate))
    return []
