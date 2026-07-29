"""Small immutable occupancy-grid helper used by masking and expert planning."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

GridIndex = tuple[int, int]


@dataclass(frozen=True, slots=True)
class OccupancyGrid:
    occupied: npt.NDArray[np.bool_]
    resolution: float
    origin_x: float = 0.0
    origin_y: float = 0.0

    def __post_init__(self) -> None:
        grid = np.asarray(self.occupied, dtype=np.bool_)
        if grid.ndim != 2 or grid.size == 0:
            raise ValueError("occupied must be a non-empty 2-D array")
        if self.resolution <= 0.0:
            raise ValueError("resolution must be positive")
        grid.setflags(write=False)
        object.__setattr__(self, "occupied", grid)

    @property
    def height(self) -> int:
        return int(self.occupied.shape[0])

    @property
    def width(self) -> int:
        return int(self.occupied.shape[1])

    def world_to_grid(self, x: float, y: float) -> GridIndex:
        column = math.floor((x - self.origin_x) / self.resolution)
        row = math.floor((y - self.origin_y) / self.resolution)
        return row, column

    def grid_to_world(self, index: GridIndex) -> tuple[float, float]:
        row, column = index
        return (
            self.origin_x + (column + 0.5) * self.resolution,
            self.origin_y + (row + 0.5) * self.resolution,
        )

    def in_bounds(self, index: GridIndex) -> bool:
        row, column = index
        return 0 <= row < self.height and 0 <= column < self.width

    def is_free(self, index: GridIndex) -> bool:
        return self.in_bounds(index) and not bool(self.occupied[index])

    def segment_is_free(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        clearance: float = 0.0,
    ) -> bool:
        if clearance < 0.0:
            raise ValueError("clearance must be non-negative")
        length = math.dist(start, end)
        steps = max(1, math.ceil(length / (0.5 * self.resolution)))
        radius_cells = math.ceil(clearance / self.resolution)
        for step in range(steps + 1):
            fraction = step / steps
            index = self.world_to_grid(
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
            row, column = index
            for dr in range(-radius_cells, radius_cells + 1):
                for dc in range(-radius_cells, radius_cells + 1):
                    if dr * dr + dc * dc > radius_cells * radius_cells:
                        continue
                    if not self.is_free((row + dr, column + dc)):
                        return False
        return True

    def connected(self, start: GridIndex, goal: GridIndex, max_cells: int = 10_000) -> bool:
        if not self.is_free(start) or not self.is_free(goal):
            return False
        queue: deque[GridIndex] = deque([start])
        visited = {start}
        while queue and len(visited) <= max_cells:
            current = queue.popleft()
            if current == goal:
                return True
            row, column = current
            for candidate in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if candidate not in visited and self.is_free(candidate):
                    visited.add(candidate)
                    queue.append(candidate)
        return False
