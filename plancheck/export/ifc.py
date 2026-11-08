"""IFC4 export (docs/PROJECT_SPEC.md §12.1).

What the file contains:

- the spatial tree: project, site, building, storey;
- walls with a body and an axis, contained in the storey;
- one ``IfcOpeningElement`` per opening that voids its wall, filled by an ``IfcDoor`` or
  ``IfcWindow``;
- rooms as ``IfcSpace`` with net and gross floor area;
- ``IfcRelSpaceBoundary`` between each space and the walls, doors, and windows around
  it, so the room graph can be rebuilt from the file alone.

Lengths are in millimetres. Heights are display defaults (see ``heights.py``).

Door placement follows the IFC convention: the door opens towards its local +y axis,
and ``SINGLE_SWING_LEFT`` / ``SINGLE_SWING_RIGHT`` say which side the hinges are on when
looking along +y.

GlobalIds are derived from element ids, so exporting the same model twice gives the same
ids and issue files keep pointing at the right elements.
"""

from __future__ import annotations

import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid
import numpy as np
from shapely.geometry import Polygon

from plancheck import __version__
from plancheck.export.heights import Heights, void_range
from plancheck.model.geometry import door_swing, opening_gap, opening_span, wall_footprint
from plancheck.model.types import EXTERIOR, BuildingModel, Opening, Point, Wall

Entity = ifcopenshell.entity_instance

CUSTOM_PSET = "PlanCheck_Element"
"""Property set for PlanCheck's own data. The ``Pset_`` prefix is reserved for buildingSMART."""

_GUID_NAMESPACE = uuid.UUID("6f1c2a54-93c1-4f0e-8a51-7d2b5a1c9e10")
_PANEL_MM = 40.0  # drawn thickness of door leaves and window panes; display only
_CUT_OVERSHOOT_MM = 1.0
_CONTACT_MM = 1.0  # how close a wall face must be to a room outline to count as bounding it
_MIN_CONTACT_MM2 = 10.0  # ignores walls that only touch a room at a corner


def ifc_guid(project_id: str, key: str) -> str:
    """A stable IFC GlobalId for ``key`` within ``project_id``."""
    return str(ifcopenshell.guid.compress(uuid.uuid5(_GUID_NAMESPACE, f"{project_id}/{key}").hex))


def _frame(origin: Point, x_dir: Point, z: float = 0.0) -> np.ndarray:
    """4x4 matrix for a frame at ``origin`` with x along ``x_dir``, y to its left, z up."""
    matrix = np.eye(4)
    matrix[:3, 0] = (x_dir[0], x_dir[1], 0.0)
    matrix[:3, 1] = (-x_dir[1], x_dir[0], 0.0)
    matrix[:3, 3] = (origin[0], origin[1], z)
    return matrix


def _opening_frame(wall: Wall, opening: Opening) -> tuple[Point, Point]:
    """Origin and x direction of an opening's local frame; +y is the side a door opens to."""
    first, second = opening_span(wall, opening)
    swing = door_swing(wall, opening)
    if swing is not None and opening.swings_to == "right":
        dx, dy = wall.direction
        return second, (-dx, -dy)
    return first, wall.direction


def _operation_type(wall: Wall, opening: Opening) -> str:
    if opening.operation == "double_swing":
        return "DOUBLE_DOOR_SINGLE_SWING"
    if opening.operation != "swing" or door_swing(wall, opening) is None:
        return "NOTDEFINED"
    # Looking along +y (the way the door opens), local x = 0 is on the left. The frame's
    # origin is the opening's start when the door swings left, and its end otherwise.
    origin_is_start = opening.swings_to == "left"
    hinge_at_origin = (opening.hinge_at == "start") == origin_is_start
    return "SINGLE_SWING_LEFT" if hinge_at_origin else "SINGLE_SWING_RIGHT"


class _Builder:
    def __init__(self, model: BuildingModel, project_id: str, heights: Heights) -> None:
        self.model = model
        self.project_id = project_id
        self.heights = heights
        self.f = ifcopenshell.api.project.create_file(version="IFC4")
        self.world: dict[int, np.ndarray] = {}
        self.keys: dict[int, str] = {}

    # ------------------------------------------------------------ low-level helpers

    def _entity(self, ifc_class: str, key: str, name: str, predefined: str | None = None) -> Entity:
        entity = ifcopenshell.api.root.create_entity(
            self.f, ifc_class=ifc_class, name=name, predefined_type=predefined
        )
        self.keys[entity.id()] = key
        return entity

    def _place(self, product: Entity, world: np.ndarray, parent: Entity | None) -> None:
        """Give ``product`` a local placement, relative to ``parent`` if there is one."""
        relative = world if parent is None else np.linalg.inv(self.world[parent.id()]) @ world
        axes = self.f.createIfcAxis2Placement3D(
            self.f.createIfcCartesianPoint([float(v) for v in relative[:3, 3]]),
            self.f.createIfcDirection([float(v) for v in relative[:3, 2]]),
            self.f.createIfcDirection([float(v) for v in relative[:3, 0]]),
        )
        product.ObjectPlacement = self.f.createIfcLocalPlacement(
            parent.ObjectPlacement if parent is not None else None, axes
        )
        self.world[product.id()] = world

    def _extrusion(self, outline: list[Point], height: float) -> Entity:
        points = [self.f.createIfcCartesianPoint([float(x), float(y)]) for x, y in outline]
        profile = self.f.createIfcArbitraryClosedProfileDef(
            "AREA", None, self.f.createIfcPolyline([*points, points[0]])
        )
        return self.f.createIfcExtrudedAreaSolid(
            profile, None, self.f.createIfcDirection([0.0, 0.0, 1.0]), float(height)
        )

    def _shape(self, product: Entity, representations: list[Entity]) -> None:
        product.Representation = self.f.createIfcProductDefinitionShape(None, None, representations)

    def _body(self, outline: list[Point], height: float) -> Entity:
        solid = self._extrusion(outline, height)
        return self.f.createIfcShapeRepresentation(self.body, "Body", "SweptSolid", [solid])

    def _pset(self, product: Entity, name: str, properties: dict[str, Any]) -> None:
        pset = ifcopenshell.api.pset.add_pset(self.f, product=product, name=name)
        ifcopenshell.api.pset.edit_pset(self.f, pset=pset, properties=properties)

    def _boundary(self, space: Entity, element: Entity, external: bool) -> None:
        self.f.create_entity(
            "IfcRelSpaceBoundary",
            GlobalId=ifcopenshell.guid.new(),
            RelatingSpace=space,
            RelatedBuildingElement=element,
            PhysicalOrVirtualBoundary="PHYSICAL",
            InternalOrExternalBoundary="EXTERNAL" if external else "INTERNAL",
        )

    # ------------------------------------------------------------ building the file

    def build(self) -> ifcopenshell.file:
        self._setup()
        walls = self._walls()
        fillings, voids = self._openings(walls)
        spaces = self._spaces()
        self._boundaries(walls, fillings, voids, spaces)
        self._assign_guids()
        return self.f

    def _setup(self) -> None:
        f = self.f
        project = self._entity("IfcProject", "project", self.project_id)
        ifcopenshell.api.unit.assign_unit(
            f,
            length={"is_metric": True, "raw": "MILLIMETERS"},
            area={"is_metric": True, "raw": "METERS"},
            volume={"is_metric": True, "raw": "METERS"},
        )
        model_context = ifcopenshell.api.context.add_context(f, context_type="Model")
        self.body = ifcopenshell.api.context.add_context(
            f,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_context,
        )
        self.axis = ifcopenshell.api.context.add_context(
            f,
            context_type="Model",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=model_context,
        )
        site = self._entity("IfcSite", "site", "Site")
        building = self._entity("IfcBuilding", "building", "Building")
        self.storey = self._entity("IfcBuildingStorey", "storey", "Level 1")
        parent: Entity | None = None
        for spatial in (site, building, self.storey):
            self._place(spatial, np.eye(4), parent)
            parent = spatial
        ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
        ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
        ifcopenshell.api.aggregate.assign_object(
            f, products=[self.storey], relating_object=building
        )

    def _custom(self, product: Entity, element: Any, extra: dict[str, Any] | None = None) -> None:
        properties = {
            "ElementId": element.id,
            "Confidence": float(element.confidence),
            "Provenance": element.provenance,
            "ExporterVersion": __version__,
        }
        self._pset(product, CUSTOM_PSET, properties | (extra or {}))

    def _walls(self) -> dict[str, Entity]:
        entities = {}
        for wall in self.model.walls:
            entity = self._entity("IfcWall", f"wall:{wall.id}", wall.id, "STANDARD")
            self._place(entity, _frame(wall.start, wall.direction), self.storey)
            half, length = wall.thickness.value_mm / 2, wall.length_mm
            # Squared-off ends, the same footprint the other exporters use.
            outline = [(-half, -half), (length + half, -half), (length + half, half), (-half, half)]
            axis_line = self.f.createIfcPolyline(
                [
                    self.f.createIfcCartesianPoint([0.0, 0.0]),
                    self.f.createIfcCartesianPoint([float(length), 0.0]),
                ]
            )
            axis = self.f.createIfcShapeRepresentation(self.axis, "Axis", "Curve2D", [axis_line])
            self._shape(entity, [axis, self._body(outline, self.heights.wall_mm)])
            self._pset(entity, "Pset_WallCommon", {"IsExternal": wall.is_exterior})
            self._custom(entity, wall, {"ThicknessSigmaMm": float(wall.thickness.sigma_mm)})
            entities[wall.id] = entity
        ifcopenshell.api.spatial.assign_container(
            self.f, products=list(entities.values()), relating_structure=self.storey
        )
        return entities

    def _openings(self, walls: dict[str, Entity]) -> tuple[dict[str, Entity], dict[str, Entity]]:
        """Returns the doors and windows, and the void elements, each keyed by opening id."""
        fillings: dict[str, Entity] = {}
        voids: dict[str, Entity] = {}
        for opening in self.model.openings:
            wall = self.model.wall(opening.wall_id)
            wall_entity = walls[wall.id]
            origin, x_dir = _opening_frame(wall, opening)
            bottom, top = void_range(opening.kind, self.heights)
            width, height = opening.width.value_mm, top - bottom
            frame = _frame(origin, x_dir, bottom)

            name = opening.id if opening.kind == "opening" else f"{opening.id} void"
            void = self._entity("IfcOpeningElement", f"void:{opening.id}", name, "OPENING")
            self._place(void, frame, wall_entity)
            reach = wall.thickness.value_mm / 2 + _CUT_OVERSHOOT_MM
            cut = [(0.0, -reach), (width, -reach), (width, reach), (0.0, reach)]
            self._shape(void, [self._body(cut, height)])
            ifcopenshell.api.feature.add_feature(self.f, feature=void, element=wall_entity)
            voids[opening.id] = void
            if opening.kind == "opening":
                continue

            if opening.kind == "door":
                filling = self._entity("IfcDoor", f"opening:{opening.id}", opening.id, "DOOR")
                filling.OperationType = _operation_type(wall, opening)
                filling.Tag = opening.tag
                self._pset(filling, "Pset_DoorCommon", {"IsExternal": wall.is_exterior})
                extra: dict[str, Any] = {"Operation": opening.operation or "unknown"}
                if opening.leaf_width is not None:
                    extra["LeafWidthMm"] = float(opening.leaf_width.value_mm)
                    extra["LeafWidthSigmaMm"] = float(opening.leaf_width.sigma_mm)
                if opening.clear_width is not None:
                    extra["ClearWidthMm"] = float(opening.clear_width.value_mm)
                    extra["ClearWidthSigmaMm"] = float(opening.clear_width.sigma_mm)
            else:
                filling = self._entity("IfcWindow", f"opening:{opening.id}", opening.id, "WINDOW")
                self._pset(filling, "Pset_WindowCommon", {"IsExternal": wall.is_exterior})
                extra = {}
            filling.OverallWidth = float(width)
            filling.OverallHeight = float(height)
            self._place(filling, frame, void)
            half = _PANEL_MM / 2
            panel = [(0.0, -half), (width, -half), (width, half), (0.0, half)]
            self._shape(filling, [self._body(panel, height)])
            ifcopenshell.api.feature.add_filling(self.f, opening=void, element=filling)
            self._custom(filling, opening, extra)
            fillings[opening.id] = filling
        if fillings:
            ifcopenshell.api.spatial.assign_container(
                self.f, products=list(fillings.values()), relating_structure=self.storey
            )
        return fillings, voids

    def _spaces(self) -> dict[str, Entity]:
        entities = {}
        for room in self.model.rooms:
            space = self._entity("IfcSpace", f"space:{room.id}", room.id, "INTERNAL")
            space.LongName = room.label
            space.CompositionType = "ELEMENT"
            self._place(space, np.eye(4), self.storey)
            self._shape(space, [self._body(room.clear_polygon, self.heights.wall_mm)])
            qto = ifcopenshell.api.pset.add_qto(
                self.f, product=space, name="Qto_SpaceBaseQuantities"
            )
            ifcopenshell.api.pset.edit_qto(
                self.f,
                qto=qto,
                properties={
                    "NetFloorArea": room.area_net_m2,
                    "GrossFloorArea": room.area_gross_m2,
                },
            )
            extra = {"RoomType": room.room_type} if room.room_type else {}
            self._custom(space, room, extra)
            entities[room.id] = space
        if entities:
            ifcopenshell.api.aggregate.assign_object(
                self.f, products=list(entities.values()), relating_object=self.storey
            )
        return entities

    def _boundaries(
        self,
        walls: dict[str, Entity],
        fillings: dict[str, Entity],
        voids: dict[str, Entity],
        spaces: dict[str, Entity],
    ) -> None:
        def touches(shape: Polygon, room_outline: Polygon) -> bool:
            contact = shape.buffer(_CONTACT_MM).intersection(room_outline)
            return bool(contact.area > _MIN_CONTACT_MM2)

        outlines = {room.id: Polygon(room.clear_polygon) for room in self.model.rooms}
        for room_id, outline in outlines.items():
            for wall in self.model.walls:
                if touches(wall_footprint(wall), outline):
                    self._boundary(spaces[room_id], walls[wall.id], wall.is_exterior)

        # Doors and cased openings bound the rooms the graph says they connect.
        connected: dict[str, set[str]] = {}
        for edge in self.model.graph.edges:
            connected.setdefault(edge.opening_id, set()).update({edge.a, edge.b})
        for opening in self.model.openings:
            wall = self.model.wall(opening.wall_id)
            element = fillings.get(opening.id, voids[opening.id])
            if opening.id in connected:
                room_ids = sorted(connected[opening.id] - {EXTERIOR})
            else:
                gap = opening_gap(wall, opening)
                room_ids = [rid for rid, outline in outlines.items() if touches(gap, outline)]
            for room_id in room_ids:
                self._boundary(spaces[room_id], element, wall.is_exterior)

    def _assign_guids(self) -> None:
        """Replace every random GlobalId with one derived from a stable key."""
        counts: Counter[str] = Counter()
        for entity in sorted(self.f.by_type("IfcRoot"), key=lambda e: e.id()):
            key = self.keys.get(entity.id())
            if key is None:
                # Relationships and property sets: numbered per class, in creation order.
                counts[entity.is_a()] += 1
                key = f"{entity.is_a()}:{counts[entity.is_a()]}"
            entity.GlobalId = ifc_guid(self.project_id, key)


def build_ifc(
    model: BuildingModel, project_id: str = "plancheck", heights: Heights | None = None
) -> ifcopenshell.file:
    """The model as an in-memory IFC4 file."""
    return _Builder(model, project_id, heights or Heights()).build()


def export_ifc(
    model: BuildingModel,
    path: str | Path,
    project_id: str = "plancheck",
    heights: Heights | None = None,
) -> Path:
    """Write the model to an IFC4 file and return its path."""
    path = Path(path)
    build_ifc(model, project_id, heights).write(str(path))
    return path
