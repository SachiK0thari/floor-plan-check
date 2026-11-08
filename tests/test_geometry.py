from __future__ import annotations

import pytest

from plancheck.model.geometry import (
    door_swing,
    drawing_bounds,
    model_bounds,
    opening_span,
    wall_footprint,
    wall_solids,
)
from plancheck.model.types import BuildingModel

# Worked out by hand for the two-room fixture (tests/conftest.py):
#   exterior ring  8200 x 4200 - 7800 x 3800            = 4 800 000 mm2
#   dividing wall  100 wide, 3800 between the wall faces =   380 000 mm2
UNCUT_AREA = 5_180_000.0
D1_GAP = 964.4 * 100.0
D2_GAP = 964.4 * 200.0
WINDOW_GAP = 1200.0 * 200.0


def test_wall_footprint_squares_off_the_ends(one_wall: BuildingModel) -> None:
    assert wall_footprint(one_wall.walls[0]).bounds == (-100.0, -100.0, 4100.0, 100.0)


def test_model_bounds(two_rooms: BuildingModel) -> None:
    assert model_bounds(two_rooms) == (-100.0, -100.0, 8100.0, 4100.0)


def test_wall_area_without_cuts(two_rooms: BuildingModel) -> None:
    area = sum(p.area for p in wall_solids(two_rooms, cut=()))
    assert area == pytest.approx(UNCUT_AREA)


def test_wall_area_with_all_openings_cut(two_rooms: BuildingModel) -> None:
    area = sum(p.area for p in wall_solids(two_rooms))
    assert area == pytest.approx(UNCUT_AREA - D1_GAP - D2_GAP - WINDOW_GAP)


def test_wall_area_with_only_doors_cut(two_rooms: BuildingModel) -> None:
    area = sum(p.area for p in wall_solids(two_rooms, cut=("door",)))
    assert area == pytest.approx(UNCUT_AREA - D1_GAP - D2_GAP)


def test_opening_span_follows_wall_direction(two_rooms: BuildingModel) -> None:
    # W3 runs from x = 8000 to x = 0, so 6000 mm along it is x = 2000.
    first, second = opening_span(two_rooms.wall("W3"), two_rooms.opening("WIN1"))
    assert first == pytest.approx((2600.0, 4000.0))
    assert second == pytest.approx((1400.0, 4000.0))


def test_door_swing_hinge_at_start_swinging_left(two_rooms: BuildingModel) -> None:
    # W5 runs up the page; its left is -x, so D1 opens into R1.
    swing = door_swing(two_rooms.wall("W5"), two_rooms.opening("D1"))
    assert swing is not None
    assert swing.hinge == pytest.approx((3950.0, 1517.8))
    assert swing.latch == pytest.approx((3950.0, 2432.2))
    assert swing.tip == pytest.approx((3035.6, 1517.8))


def test_door_swing_hinge_at_end_swinging_left(two_rooms: BuildingModel) -> None:
    # W1 runs left to right; its left is +y, so D2 opens into the building.
    swing = door_swing(two_rooms.wall("W1"), two_rooms.opening("D2"))
    assert swing is not None
    assert swing.hinge == pytest.approx((6482.2, 100.0))
    assert swing.latch == pytest.approx((5567.8, 100.0))
    assert swing.tip == pytest.approx((6482.2, 1014.4))


def test_door_swing_is_none_when_swing_is_unknown(two_rooms: BuildingModel) -> None:
    door = two_rooms.opening("D1").model_copy(update={"swings_to": None})
    assert door_swing(two_rooms.wall("W5"), door) is None
    assert door_swing(two_rooms.wall("W3"), two_rooms.opening("WIN1")) is None


def test_drawing_bounds_include_outward_door_swings(two_rooms: BuildingModel) -> None:
    # Flip D2 to open outwards: its leaf tip is 914.4 mm below the outer wall face.
    doors = [
        o.model_copy(update={"swings_to": "right"}) if o.id == "D2" else o
        for o in two_rooms.openings
    ]
    model = two_rooms.model_copy(update={"openings": doors})
    assert drawing_bounds(two_rooms) == model_bounds(two_rooms)
    assert drawing_bounds(model) == pytest.approx((-100.0, -1014.4, 8100.0, 4100.0))
