"""Hand-built models whose geometry is simple enough to work out on paper."""

from __future__ import annotations

from typing import Any

import pytest

from plancheck.model.types import (
    EXTERIOR,
    BuildingModel,
    GraphEdge,
    Measured,
    Opening,
    Room,
    RoomGraph,
    Wall,
)

LEAF_MM = 914.4  # a 36 in leaf
GAP_MM = LEAF_MM + 50.0


def exact(value_mm: float) -> Measured:
    return Measured(value_mm=value_mm, sigma_mm=0.0, source="user")


def wall(
    wall_id: str, start: tuple[float, float], end: tuple[float, float], thickness: float
) -> Wall:
    return Wall(
        id=wall_id,
        start=start,
        end=end,
        thickness=exact(thickness),
        is_exterior=thickness == 200.0,
        provenance="user_edit",
    )


def two_room_parts() -> dict[str, Any]:
    """An 8000 x 4000 mm outline split into two rooms at x = 4000.

    Exterior walls are 200 mm thick and run counter-clockwise; the dividing wall is 100 mm.
    D1 joins the rooms, D2 leads outside from R2, and R1 has one window.
    """
    walls = [
        wall("W1", (0, 0), (8000, 0), 200.0),
        wall("W2", (8000, 0), (8000, 4000), 200.0),
        wall("W3", (8000, 4000), (0, 4000), 200.0),
        wall("W4", (0, 4000), (0, 0), 200.0),
        wall("W5", (4000, 0), (4000, 4000), 100.0),
    ]
    openings = [
        Opening(
            id="D1",
            kind="door",
            wall_id="W5",
            position_along_wall_mm=2000.0,
            width=exact(GAP_MM),
            leaf_width=exact(LEAF_MM),
            operation="swing",
            hinge_at="start",
            swings_to="left",
            tag="01",
            provenance="user_edit",
        ),
        Opening(
            id="D2",
            kind="door",
            wall_id="W1",
            position_along_wall_mm=6000.0,
            width=exact(GAP_MM),
            leaf_width=exact(LEAF_MM),
            operation="swing",
            hinge_at="end",
            swings_to="left",
            tag="02",
            provenance="user_edit",
        ),
        Opening(
            id="WIN1",
            kind="window",
            wall_id="W3",
            position_along_wall_mm=6000.0,  # W3 runs right to left, so this is x = 2000
            width=exact(1200.0),
            provenance="user_edit",
        ),
    ]
    rooms = [
        Room(
            id="R1",
            boundary=[(0, 0), (4000, 0), (4000, 4000), (0, 4000)],
            clear_polygon=[(100, 100), (3950, 100), (3950, 3900), (100, 3900)],
            label="OFFICE",
            room_type="office",
            provenance="user_edit",
        ),
        Room(
            id="R2",
            boundary=[(4000, 0), (8000, 0), (8000, 4000), (4000, 4000)],
            clear_polygon=[(4050, 100), (7900, 100), (7900, 3900), (4050, 3900)],
            label="RECEPTION",
            room_type="reception",
            provenance="user_edit",
        ),
    ]
    return {"walls": walls, "openings": openings, "rooms": rooms}


@pytest.fixture
def two_rooms() -> BuildingModel:
    parts = two_room_parts()
    graph = RoomGraph(
        nodes=["R1", "R2", EXTERIOR],
        edges=[
            GraphEdge(opening_id="D1", a="R1", b="R2"),
            GraphEdge(opening_id="D2", a="R2", b=EXTERIOR),
        ],
    )
    return BuildingModel(**parts, graph=graph)


@pytest.fixture
def one_wall() -> BuildingModel:
    """A single 4000 mm wall, 200 mm thick, along the x axis."""
    return BuildingModel(walls=[wall("W1", (0, 0), (4000, 0), 200.0)])
