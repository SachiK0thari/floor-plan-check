from __future__ import annotations

from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.validate
import pytest

from plancheck.export.heights import Heights
from plancheck.export.ifc import CUSTOM_PSET, build_ifc, export_ifc, ifc_guid
from plancheck.ingest.ifc import read_room_graph
from plancheck.model.types import EXTERIOR, BuildingModel, Measured, Opening, RoomGraph
from plancheck.synthetic.generator import generate_model


def edge_set(graph: RoomGraph) -> set[tuple[str, frozenset[str]]]:
    """Edges without regard to which end is listed first."""
    return {(edge.opening_id, frozenset((edge.a, edge.b))) for edge in graph.edges}


def schema_errors(f: ifcopenshell.file) -> list[str]:
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, logger, express_rules=True)
    return [str(statement.get("message", statement)) for statement in logger.statements]


def by_name(f: ifcopenshell.file, ifc_class: str, name: str) -> ifcopenshell.entity_instance:
    return next(e for e in f.by_type(ifc_class) if e.Name == name)


# ---------------------------------------------------------------- validity


def test_ifc_passes_schema_validation(two_rooms: BuildingModel) -> None:
    assert schema_errors(build_ifc(two_rooms)) == []


@pytest.mark.parametrize("seed", range(3))
def test_generated_plans_pass_schema_validation(seed: int) -> None:
    assert schema_errors(build_ifc(generate_model(seed))) == []


def test_ifc_survives_writing_and_reading(two_rooms: BuildingModel, tmp_path: Path) -> None:
    f = ifcopenshell.open(str(export_ifc(two_rooms, tmp_path / "plan.ifc")))
    assert f.schema == "IFC4"
    assert schema_errors(f) == []


# ---------------------------------------------------------------- structure


def test_spatial_tree(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    storey = f.by_type("IfcBuildingStorey")[0]
    chain = []
    parent = ifcopenshell.util.element.get_aggregate(storey)
    while parent is not None:
        chain.append(parent.is_a())
        parent = ifcopenshell.util.element.get_aggregate(parent)
    assert chain == ["IfcBuilding", "IfcSite", "IfcProject"]
    for ifc_class in ("IfcWall", "IfcDoor", "IfcWindow"):
        for element in f.by_type(ifc_class):
            assert ifcopenshell.util.element.get_container(element) == storey
    for space in f.by_type("IfcSpace"):
        assert ifcopenshell.util.element.get_aggregate(space) == storey


def test_doors_and_windows_fill_openings_that_void_their_wall(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    expected_wall = {"D1": "W5", "D2": "W1", "WIN1": "W3"}
    for ifc_class in ("IfcDoor", "IfcWindow"):
        for filling in f.by_type(ifc_class):
            void = filling.FillsVoids[0].RelatingOpeningElement
            assert void.is_a("IfcOpeningElement")
            assert void.VoidsElements[0].RelatingBuildingElement.Name == expected_wall[filling.Name]


def test_lengths_are_millimetres(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    length = next(u for u in f.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT")
    assert (length.Prefix, length.Name) == ("MILLI", "METRE")
    assert by_name(f, "IfcDoor", "D1").OverallWidth == pytest.approx(964.4)


def test_space_quantities_and_custom_properties(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    space = by_name(f, "IfcSpace", "R1")
    assert space.LongName == "OFFICE"
    psets = ifcopenshell.util.element.get_psets(space)
    assert psets["Qto_SpaceBaseQuantities"]["NetFloorArea"] == pytest.approx(14.63)
    assert psets["Qto_SpaceBaseQuantities"]["GrossFloorArea"] == pytest.approx(16.0)
    assert psets[CUSTOM_PSET]["Provenance"] == "user_edit"
    assert psets[CUSTOM_PSET]["RoomType"] == "office"

    door = ifcopenshell.util.element.get_psets(by_name(f, "IfcDoor", "D2"))
    assert door["Pset_DoorCommon"]["IsExternal"] is True
    assert door[CUSTOM_PSET]["LeafWidthMm"] == pytest.approx(914.4)
    assert not CUSTOM_PSET.startswith("Pset_")  # that prefix is reserved for standard sets


# ---------------------------------------------------------------- geometry


def test_wall_volume_has_the_door_cut_out(two_rooms: BuildingModel) -> None:
    # W5: footprint 100 x (4000 + 2 x 50) mm, 2700 high, less a 964.4 x 100 x 2100 door.
    f = build_ifc(two_rooms, heights=Heights(wall_mm=2700.0, door_head_mm=2100.0))
    shape: Any = ifcopenshell.geom.create_shape(
        ifcopenshell.geom.settings(), by_name(f, "IfcWall", "W5")
    )
    expected_m3 = (100.0 * 4100.0 * 2700.0 - 964.4 * 100.0 * 2100.0) / 1e9
    assert ifcopenshell.util.shape.get_volume(shape.geometry) == pytest.approx(expected_m3)


def test_wall_and_door_placements(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    wall = ifcopenshell.util.placement.get_local_placement(
        by_name(f, "IfcWall", "W3").ObjectPlacement
    )
    assert wall[:3, 3] == pytest.approx((8000.0, 4000.0, 0.0))  # starts at the wall's start
    assert wall[:3, 0] == pytest.approx((-1.0, 0.0, 0.0))  # x runs along the wall

    window = by_name(f, "IfcWindow", "WIN1")
    placement = ifcopenshell.util.placement.get_local_placement(window.ObjectPlacement)
    assert placement[:3, 3] == pytest.approx((2600.0, 4000.0, 900.0))  # sits on the sill


def test_door_swing_follows_the_ifc_convention(two_rooms: BuildingModel) -> None:
    # A door opens towards its local +y; LEFT/RIGHT is the hinge side looking along +y.
    f = build_ifc(two_rooms)

    d1 = by_name(f, "IfcDoor", "D1")  # opens into R1 (-x), hinge at the low-y end
    placement = ifcopenshell.util.placement.get_local_placement(d1.ObjectPlacement)
    assert placement[:3, 1] == pytest.approx((-1.0, 0.0, 0.0))
    assert placement[:3, 3] == pytest.approx((4000.0, 1517.8, 0.0))
    assert d1.OperationType == "SINGLE_SWING_LEFT"

    d2 = by_name(f, "IfcDoor", "D2")  # opens into the building (+y), hinge at the high-x end
    placement = ifcopenshell.util.placement.get_local_placement(d2.ObjectPlacement)
    assert placement[:3, 1] == pytest.approx((0.0, 1.0, 0.0))
    assert placement[:3, 3] == pytest.approx((5517.8, 0.0, 0.0))
    assert d2.OperationType == "SINGLE_SWING_RIGHT"


@pytest.mark.parametrize(
    ("hinge_at", "swings_to", "expected"),
    [
        ("start", "left", "SINGLE_SWING_LEFT"),
        ("end", "left", "SINGLE_SWING_RIGHT"),
        # Swinging right turns the viewer around, so the hinge changes sides.
        ("start", "right", "SINGLE_SWING_RIGHT"),
        ("end", "right", "SINGLE_SWING_LEFT"),
    ],
)
def test_all_four_door_configurations(
    two_rooms: BuildingModel, hinge_at: str, swings_to: str, expected: str
) -> None:
    doors = [
        o.model_copy(update={"hinge_at": hinge_at, "swings_to": swings_to}) if o.id == "D1" else o
        for o in two_rooms.openings
    ]
    f = build_ifc(two_rooms.model_copy(update={"openings": doors}))
    door = by_name(f, "IfcDoor", "D1")
    placement = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
    # W5 runs up the page, so its left is -x.
    assert placement[0, 1] == pytest.approx(-1.0 if swings_to == "left" else 1.0)
    assert door.OperationType == expected
    assert schema_errors(f) == []


def test_door_with_unknown_swing_is_not_given_one(two_rooms: BuildingModel) -> None:
    doors = [
        o.model_copy(update={"hinge_at": None}) if o.id == "D1" else o for o in two_rooms.openings
    ]
    f = build_ifc(two_rooms.model_copy(update={"openings": doors}))
    assert by_name(f, "IfcDoor", "D1").OperationType == "NOTDEFINED"


# ---------------------------------------------------------------- round trip


def test_space_boundaries(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)

    def bounding(space_name: str) -> set[str]:
        space = by_name(f, "IfcSpace", space_name)
        return {rel.RelatedBuildingElement.Name for rel in space.BoundedBy}

    assert bounding("R1") == {"W1", "W3", "W4", "W5", "D1", "WIN1"}
    assert bounding("R2") == {"W1", "W2", "W3", "W5", "D1", "D2"}
    d2 = by_name(f, "IfcDoor", "D2")
    assert [rel.InternalOrExternalBoundary for rel in d2.ProvidesBoundaries] == ["EXTERNAL"]


def test_room_graph_round_trip(two_rooms: BuildingModel, tmp_path: Path) -> None:
    graph = read_room_graph(export_ifc(two_rooms, tmp_path / "plan.ifc"))
    assert set(graph.nodes) == set(two_rooms.graph.nodes)
    assert edge_set(graph) == edge_set(two_rooms.graph)


@pytest.mark.parametrize("seed", range(25))
def test_room_graph_round_trip_on_generated_plans(seed: int) -> None:
    model = generate_model(seed)
    graph = read_room_graph(build_ifc(model))
    assert set(graph.nodes) == set(model.graph.nodes)
    assert edge_set(graph) == edge_set(model.graph)


def test_cased_opening_round_trips_as_a_passage(two_rooms: BuildingModel) -> None:
    # Replace door D1 with an opening that has no door in it.
    cased = Opening(
        id="D1",
        kind="opening",
        wall_id="W5",
        position_along_wall_mm=2000.0,
        width=Measured(value_mm=964.4, sigma_mm=0.0, source="user"),
        provenance="user_edit",
    )
    openings = [cased if o.id == "D1" else o for o in two_rooms.openings]
    f = build_ifc(two_rooms.model_copy(update={"openings": openings}))
    assert {d.Name for d in f.by_type("IfcDoor")} == {"D2"}
    assert edge_set(read_room_graph(f)) == edge_set(two_rooms.graph)
    assert schema_errors(f) == []


# ---------------------------------------------------------------- GlobalIds


def test_global_ids_are_stable_and_unique(two_rooms: BuildingModel) -> None:
    first = build_ifc(two_rooms, project_id="plan-a")
    second = build_ifc(two_rooms, project_id="plan-a")
    other = build_ifc(two_rooms, project_id="plan-b")

    def ids(f: ifcopenshell.file) -> list[str]:
        return [e.GlobalId for e in sorted(f.by_type("IfcRoot"), key=lambda e: e.id())]

    assert ids(first) == ids(second)
    assert len(set(ids(first))) == len(ids(first))
    assert not set(ids(first)) & set(ids(other))
    assert by_name(first, "IfcWall", "W5").GlobalId == ifc_guid("plan-a", "wall:W5")
    assert by_name(first, "IfcDoor", "D1").GlobalId == ifc_guid("plan-a", "opening:D1")


def test_element_ids_do_not_shift_when_the_model_grows(two_rooms: BuildingModel) -> None:
    # Dropping the window changes how many relationships exist, but W5 keeps its id.
    without = two_rooms.model_copy(
        update={"openings": [o for o in two_rooms.openings if o.id != "WIN1"]}
    )
    a, b = build_ifc(two_rooms, "p"), build_ifc(without, "p")
    for ifc_class, name in (("IfcWall", "W5"), ("IfcDoor", "D2"), ("IfcSpace", "R2")):
        assert by_name(a, ifc_class, name).GlobalId == by_name(b, ifc_class, name).GlobalId


def test_exterior_is_not_a_space(two_rooms: BuildingModel) -> None:
    f = build_ifc(two_rooms)
    assert EXTERIOR not in {space.Name for space in f.by_type("IfcSpace")}
