import numpy as np
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.astar import astar


def test_astar_routes_through_gap_without_corner_cutting() -> None:
    occupied = np.zeros((10, 10), dtype=np.bool_)
    occupied[5, :] = True
    occupied[5, 7] = False
    grid = OccupancyGrid(occupied, 1.0)
    path = astar(grid, (2, 2), (8, 8))
    assert path[0] == (2, 2)
    assert path[-1] == (8, 8)
    assert (5, 7) in path
    assert all(grid.is_free(index) for index in path)


def test_astar_returns_empty_for_occupied_goal() -> None:
    occupied = np.zeros((4, 4), dtype=np.bool_)
    occupied[3, 3] = True
    assert astar(OccupancyGrid(occupied, 1.0), (0, 0), (3, 3)) == []
