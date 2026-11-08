from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from plancheck.model.types import (
    EXTERIOR,
    BuildingModel,
    GraphEdge,
    Opening,
    Room,
    RoomGraph,
    Transform,
)
from tests.conftest import exact, two_room_parts, wall


def test_wall_vectors() -> None:
    w = wall("W", (0, 0), (0, 3000), 100.0)
    assert w.length_mm == 3000
    assert w.direction == (0, 1)
    assert w.left_normal == (-1, 0)  # left of "up" is "towards -x"
    assert w.point_at(1200) == (0, 1200)


def test_wall_rejects_zero_length() -> None:
    with pytest.raises(ValidationError, match="same point"):
        wall("W", (5, 5), (5, 5), 100.0)


def test_room_areas_are_computed_from_polygons(two_rooms: BuildingModel) -> None:
    room = two_rooms.room("R1")
    assert room.area_gross_m2 == pytest.approx(16.0)
    assert room.area_net_m2 == pytest.approx(3.85 * 3.8)


def test_room_rejects_clear_polygon_outside_boundary() -> None:
    with pytest.raises(ValidationError, match="inside boundary"):
        Room(
            id="R",
            boundary=[(0, 0), (1000, 0), (1000, 1000), (0, 1000)],
            clear_polygon=[(0, 0), (2000, 0), (2000, 1000), (0, 1000)],
            provenance="user_edit",
        )


def test_json_round_trip(two_rooms: BuildingModel) -> None:
    text = two_rooms.model_dump_json()
    assert '"area_net_m2"' in text  # areas are in the output for API consumers
    assert BuildingModel.model_validate_json(text) == two_rooms


def test_stored_area_cannot_override_geometry(two_rooms: BuildingModel) -> None:
    data = two_rooms.model_dump(mode="json")
    data["rooms"][0]["area_net_m2"] = 999.0
    assert BuildingModel.model_validate(data).room("R1").area_net_m2 == pytest.approx(14.63)


def test_models_are_immutable(two_rooms: BuildingModel) -> None:
    with pytest.raises(ValidationError):
        two_rooms.px_per_mm = 2.0  # type: ignore[misc]


def test_window_cannot_have_door_fields() -> None:
    with pytest.raises(ValidationError, match="only apply to doors"):
        Opening(
            id="N",
            kind="window",
            wall_id="W",
            position_along_wall_mm=500,
            width=exact(900),
            hinge_at="start",
            provenance="user_edit",
        )


def _door(**overrides: Any) -> Opening:
    fields: dict[str, Any] = {
        "id": "X",
        "kind": "door",
        "wall_id": "W5",
        "position_along_wall_mm": 500.0,
        "width": exact(900.0),
        "provenance": "user_edit",
    }
    return Opening(**(fields | overrides))


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (_door(wall_id="nope"), "unknown wall"),
        (_door(position_along_wall_mm=3900.0), "extends past the ends"),
        (_door(position_along_wall_mm=2400.0), "overlap"),  # D1 spans 1517.8 to 2482.2
        (_door(id="D1", position_along_wall_mm=600.0), "duplicate element ids"),
    ],
)
def test_model_rejects_bad_openings(extra: Opening, message: str) -> None:
    parts = two_room_parts()
    parts["openings"].append(extra)
    with pytest.raises(ValidationError, match=message):
        BuildingModel(**parts)


def test_openings_may_touch_but_not_overlap() -> None:
    parts = two_room_parts()
    # D1 ends at 2482.2; a 900 mm opening centred at 2932.2 starts exactly there.
    parts["openings"].append(_door(position_along_wall_mm=2932.2))
    BuildingModel(**parts)


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        (RoomGraph(nodes=["R1", "R9"]), "not rooms"),
        (
            RoomGraph(nodes=["R1", "R2"], edges=[GraphEdge(opening_id="D9", a="R1", b="R2")]),
            "unknown opening",
        ),
        (
            RoomGraph(nodes=["R1"], edges=[GraphEdge(opening_id="D1", a="R1", b="R2")]),
            "must be graph nodes",
        ),
    ],
)
def test_model_rejects_bad_graph(graph: RoomGraph, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        BuildingModel(**two_room_parts(), graph=graph)


def test_graph_to_networkx(two_rooms: BuildingModel) -> None:
    import networkx as nx

    graph = two_rooms.graph.to_networkx()
    assert nx.shortest_path(graph, "R1", EXTERIOR) == ["R1", "R2", EXTERIOR]
    assert graph.get_edge_data("R1", "R2") == {"D1": {"opening_id": "D1"}}


def test_transform_affine_round_trip() -> None:
    # 0.1 px per mm, y flipped, image 500 px tall with a 40 px margin.
    t = Transform(matrix=((10.0, 0.0, -400.0), (0.0, -10.0, 4600.0), (0.0, 0.0, 1.0)))
    assert t.kind == "affine"
    assert t.apply((40.0, 460.0)) == pytest.approx((0.0, 0.0))
    assert t.inverse().apply((0.0, 0.0)) == pytest.approx((40.0, 460.0))


def test_transform_homography_divides_by_w() -> None:
    t = Transform(matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.001, 0.0, 1.0)))
    assert t.kind == "homography"
    assert t.apply((1000.0, 500.0)) == pytest.approx((500.0, 250.0))


def test_transform_rejects_singular_matrix() -> None:
    with pytest.raises(ValidationError, match="singular"):
        Transform(matrix=((1.0, 2.0, 0.0), (2.0, 4.0, 0.0), (0.0, 0.0, 1.0)))
