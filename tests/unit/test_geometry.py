import math

import pytest
from ramp_core.geometry import (
    nearest_polyline_tangent_heading,
    normalize_angle,
    parse_shelf_boxes,
    point_to_oriented_box_distance,
    robot_to_world,
    world_to_robot,
)
from ramp_core.types import Pose2D


def test_coordinate_transforms_round_trip() -> None:
    robot = Pose2D(2.0, -1.0, math.pi / 3.0)
    local = (0.7, -0.2)
    world = robot_to_world(local, robot)
    assert world_to_robot(world, robot) == pytest.approx(local)


def test_normalize_angle_half_open_interval() -> None:
    assert normalize_angle(math.pi) == pytest.approx(-math.pi)
    assert normalize_angle(3.0 * math.pi) == pytest.approx(-math.pi)


def test_nearest_polyline_tangent_tracks_straight_and_turning_paths() -> None:
    assert nearest_polyline_tangent_heading((1.0, 0.4), ((0.0, 0.0), (2.0, 0.0))) == pytest.approx(
        0.0
    )
    turning = ((0.0, 0.0), (1.0, 0.0), (1.0, 2.0))
    assert nearest_polyline_tangent_heading((0.7, 0.0), turning) == pytest.approx(0.0)
    assert nearest_polyline_tangent_heading((1.0, 0.0), turning) == pytest.approx(math.pi / 2.0)
    assert nearest_polyline_tangent_heading((1.2, 1.0), turning) == pytest.approx(math.pi / 2.0)


def test_nearest_polyline_tangent_handles_degenerate_and_invalid_paths() -> None:
    assert nearest_polyline_tangent_heading((0.0, 0.0), ((0.0, 0.0),)) is None
    assert (
        nearest_polyline_tangent_heading((0.0, 0.0), ((1.0, 1.0), (1.0, 1.0), (1.0, 1.0))) is None
    )
    with pytest.raises(ValueError, match="finite"):
        nearest_polyline_tangent_heading((math.nan, 0.0), ((0.0, 0.0), (1.0, 0.0)))


def test_point_to_oriented_box_distance_handles_inside_edge_and_rotation() -> None:
    assert point_to_oriented_box_distance((0.0, 0.0), (0.0, 0.0), (1.0, 0.5)) == 0.0
    assert point_to_oriented_box_distance((1.3, 0.0), (0.0, 0.0), (1.0, 0.5)) == pytest.approx(0.3)
    assert point_to_oriented_box_distance(
        (0.0, 1.3), (0.0, 0.0), (1.0, 0.5), math.pi / 2.0
    ) == pytest.approx(0.3)


def test_point_to_oriented_box_distance_rejects_negative_extent() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        point_to_oriented_box_distance((0.0, 0.0), (0.0, 0.0), (-1.0, 0.5))


def test_parse_shelf_boxes_applies_model_local_offset() -> None:
    boxes = parse_shelf_boxes('[{"model":"shelf","pos":[2.0,3.0,0.0]}]')
    assert len(boxes) == 1
    assert boxes[0] == pytest.approx((2.0, 2.805, 0.45, 0.20, 0.0))


def test_parse_shelf_boxes_rejects_unsupported_geometry() -> None:
    with pytest.raises(ValueError, match="only shelf"):
        parse_shelf_boxes('[{"model":"unknown","pos":[0.0,0.0,0.0]}]')
