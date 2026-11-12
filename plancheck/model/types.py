"""BuildingModel: the central data contract (docs/PROJECT_SPEC.md §5).

Units are millimetres. Plan space has its origin at the bottom-left, x to the right and
y up. Image space (pixels) has its origin at the top-left and y down; ``Transform`` maps
between the two.

Models are immutable. A correction produces a new model (``model_copy(update=...)``),
which is what makes model versions append-only.
"""

from __future__ import annotations

import math
from datetime import date
from itertools import pairwise
from typing import Annotated, Any, Literal, Self

import networkx as nx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from shapely.geometry import Polygon

from plancheck.jurisdiction.location_evidence import LocationExtraction

EXTERIOR = "exterior"
"""Graph node id for the outside of the building."""

_TOL_MM = 1e-6

Point = tuple[float, float]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Provenance = Literal["model", "ocr", "vector_import", "user_edit", "synthetic"]
MeasureSource = Literal["geometry", "nominal_snap", "schedule", "dimension_text", "user"]
OpeningKind = Literal["door", "window", "opening"]
DoorOperation = Literal["swing", "double_swing", "sliding", "pocket", "folding", "none"]
ScaleSource = Literal["exact", "pdf_vector", "dimensions", "room_areas", "scale_bar", "user"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Measured(_Base):
    """A length with its standard uncertainty and where it came from."""

    value_mm: float = Field(allow_inf_nan=False)
    sigma_mm: float = Field(ge=0.0, allow_inf_nan=False)
    source: MeasureSource


class Wall(_Base):
    """A straight wall, stored as a directed centerline (start to end) with a thickness."""

    id: str
    start: Point
    end: Point
    thickness: Measured
    is_exterior: bool = False
    confidence: Confidence = 1.0
    provenance: Provenance

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.length_mm <= _TOL_MM:
            raise ValueError(f"wall {self.id}: start and end are the same point")
        if self.thickness.value_mm <= 0:
            raise ValueError(f"wall {self.id}: thickness must be positive")
        return self

    @property
    def length_mm(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def direction(self) -> Point:
        """Unit vector from start to end."""
        length = self.length_mm
        return ((self.end[0] - self.start[0]) / length, (self.end[1] - self.start[1]) / length)

    @property
    def left_normal(self) -> Point:
        """Unit vector pointing to the left of the directed wall (direction turned +90°)."""
        dx, dy = self.direction
        return (-dy, dx)

    def point_at(self, distance_mm: float) -> Point:
        """Point on the centerline at ``distance_mm`` from ``start``."""
        dx, dy = self.direction
        return (self.start[0] + dx * distance_mm, self.start[1] + dy * distance_mm)


class Opening(_Base):
    """A door, window, or cased opening in a wall.

    ``position_along_wall_mm`` is the distance from the wall's start to the centre of the
    opening. ``width`` is the extent of the gap in the wall, measured along the wall.
    ``hinge_at`` and ``swings_to`` are defined against the directed wall, so they are
    unambiguous: the hinge is at the end of the opening nearer the wall's ``start`` or
    ``end``, and the leaf opens to the wall's left or right side.
    """

    id: str
    kind: OpeningKind
    wall_id: str
    position_along_wall_mm: float = Field(ge=0.0, allow_inf_nan=False)
    width: Measured
    leaf_width: Measured | None = None
    clear_width: Measured | None = None
    operation: DoorOperation | None = None
    hinge_at: Literal["start", "end"] | None = None
    swings_to: Literal["left", "right"] | None = None
    tag: str | None = None
    confidence: Confidence = 1.0
    provenance: Provenance

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.width.value_mm <= 0:
            raise ValueError(f"opening {self.id}: width must be positive")
        if self.kind != "door":
            door_only = {
                "leaf_width": self.leaf_width,
                "clear_width": self.clear_width,
                "operation": self.operation,
                "hinge_at": self.hinge_at,
                "swings_to": self.swings_to,
            }
            present = [name for name, value in door_only.items() if value is not None]
            if present:
                raise ValueError(f"opening {self.id}: {present} only apply to doors")
        return self


def _polygon(points: list[Point], what: str) -> Polygon:
    poly = Polygon(points)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError(f"{what} is not a valid polygon")
    return poly


class Room(_Base):
    """A room with two outlines.

    ``boundary`` runs along wall centerlines (gross). ``clear_polygon`` runs along wall
    faces (net) and is the one compliance checks use. Polygons are open rings: the first
    point is not repeated at the end. Areas are computed from the polygons, never stored.
    """

    id: str
    boundary: list[Point] = Field(min_length=3)
    clear_polygon: list[Point] = Field(min_length=3)
    label: str | None = None
    room_type: str | None = None
    space_function: str | None = None
    corridor_paths: list[list[Point]] = Field(default_factory=list)
    """User/importer supplied travel paths covering every corridor arm, in millimetres."""
    confidence: Confidence = 1.0
    provenance: Provenance

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data: Any) -> Any:
        # Areas appear in serialized output; drop them on the way back in and recompute.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in ("area_net_m2", "area_gross_m2")}
        return data

    @model_validator(mode="after")
    def _check(self) -> Self:
        gross = _polygon(self.boundary, f"room {self.id}: boundary")
        net = _polygon(self.clear_polygon, f"room {self.id}: clear_polygon")
        if not gross.buffer(1e-3).contains(net):
            raise ValueError(f"room {self.id}: clear_polygon must lie inside boundary")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def area_net_m2(self) -> float:
        return float(Polygon(self.clear_polygon).area) / 1e6

    @computed_field  # type: ignore[prop-decorator]
    @property
    def area_gross_m2(self) -> float:
        return float(Polygon(self.boundary).area) / 1e6


class Fixture(_Base):
    """Something that occupies floor area: a toilet, a lavatory, casework."""

    id: str
    kind: str
    footprint: list[Point] = Field(min_length=3)
    room_id: str
    confidence: Confidence = 1.0
    provenance: Provenance

    @model_validator(mode="after")
    def _check(self) -> Self:
        _polygon(self.footprint, f"fixture {self.id}: footprint")
        return self


class Dimension(_Base):
    """A dimension string read from the drawing. ``p1`` and ``p2`` are the dimension line ends."""

    id: str
    text: str
    value_mm: float = Field(gt=0.0, allow_inf_nan=False)
    p1: Point
    p2: Point
    confidence: Confidence = 1.0
    provenance: Provenance


class GraphEdge(_Base):
    """An opening that connects two graph nodes (room ids or ``EXTERIOR``)."""

    opening_id: str
    a: str
    b: str


class RoomGraph(_Base):
    """Connectivity: nodes are room ids plus ``EXTERIOR``; edges are openings."""

    nodes: list[str] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def to_networkx(self) -> nx.MultiGraph:
        graph = nx.MultiGraph()
        graph.add_nodes_from(self.nodes)
        for edge in self.edges:
            graph.add_edge(edge.a, edge.b, key=edge.opening_id, opening_id=edge.opening_id)
        return graph


class ProjectContext(_Base):
    """Facts about the project that are not drawn on the plan.

    They are entered by the user, except that the jurisdiction may be proposed from the
    site address (``plancheck.jurisdiction``); ``jurisdiction_source`` records which, and
    results under an unconfirmed proposal are labelled provisional.
    """

    country: str | None = None
    region: str | None = None
    city: str | None = None
    planning_authority: str | None = None
    ada_reference: bool = False
    site_address: str | None = None
    jurisdiction: str | None = None
    jurisdiction_source: Literal["user", "address_proposed", "address_confirmed"] | None = None
    facility_type: str | None = None
    occupancy: str | None = None
    sprinklered: bool | None = None
    work_type: Literal["new", "alteration", "existing"] | None = None
    permit_date: date | None = None


Row3 = tuple[float, float, float]


class Transform(_Base):
    """Maps image pixels to plan millimetres, as a 3x3 homogeneous matrix.

    A last row of (0, 0, 1) makes it an affine map (scale, rotation, flip, offset). Any
    other last row makes it a homography, which a photographed plan needs.
    """

    matrix: tuple[Row3, Row3, Row3]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if abs(float(np.linalg.det(np.array(self.matrix)))) < 1e-12:
            raise ValueError("transform matrix is singular")
        return self

    @property
    def kind(self) -> Literal["affine", "homography"]:
        return "affine" if self.matrix[2] == (0.0, 0.0, 1.0) else "homography"

    def apply(self, point: Point) -> Point:
        x, y, w = np.array(self.matrix) @ np.array([point[0], point[1], 1.0])
        return (float(x / w), float(y / w))

    def inverse(self) -> Transform:
        inv = np.linalg.inv(np.array(self.matrix))
        rows = tuple(tuple(float(v) for v in row) for row in inv)
        return Transform.model_validate({"matrix": rows})


class BuildingModel(_Base):
    """One floor of a building: geometry, connectivity, scale, and project context."""

    schema_version: Literal[1] = 1
    source_image: str | None = None
    image_to_model: Transform | None = None
    px_per_mm: float | None = Field(default=None, gt=0.0)
    scale_rel_sigma: float | None = Field(default=None, ge=0.0)
    scale_x_over_y: float | None = Field(default=None, gt=0.0)
    scale_source: ScaleSource | None = None
    project: ProjectContext = Field(default_factory=ProjectContext)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    fixtures: list[Fixture] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    graph: RoomGraph = Field(default_factory=RoomGraph)
    location_extraction: LocationExtraction | None = None
    warnings: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Self:
        self._check_unique_ids()
        self._check_openings()
        self._check_references()
        return self

    def _check_unique_ids(self) -> None:
        ids = [
            element.id
            for group in (self.walls, self.openings, self.rooms, self.fixtures, self.dimensions)
            for element in group
        ]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate element ids: {duplicates}")
        if EXTERIOR in ids:
            raise ValueError(f"'{EXTERIOR}' is reserved and cannot be an element id")

    def _check_openings(self) -> None:
        walls = {wall.id: wall for wall in self.walls}
        spans: dict[str, list[tuple[float, float, str]]] = {}
        for opening in self.openings:
            wall = walls.get(opening.wall_id)
            if wall is None:
                raise ValueError(f"opening {opening.id}: unknown wall {opening.wall_id}")
            half = opening.width.value_mm / 2
            lo, hi = opening.position_along_wall_mm - half, opening.position_along_wall_mm + half
            if lo < -_TOL_MM or hi > wall.length_mm + _TOL_MM:
                raise ValueError(f"opening {opening.id}: extends past the ends of wall {wall.id}")
            spans.setdefault(wall.id, []).append((lo, hi, opening.id))
        for wall_id, wall_spans in spans.items():
            wall_spans.sort()
            for (_, hi, first), (lo, _, second) in pairwise(wall_spans):
                if lo < hi - _TOL_MM:
                    raise ValueError(f"openings {first} and {second} overlap on wall {wall_id}")

    def _check_references(self) -> None:
        room_ids = {room.id for room in self.rooms}
        opening_ids = {opening.id for opening in self.openings}
        for fixture in self.fixtures:
            if fixture.room_id not in room_ids:
                raise ValueError(f"fixture {fixture.id}: unknown room {fixture.room_id}")
        unknown_nodes = sorted(set(self.graph.nodes) - room_ids - {EXTERIOR})
        if unknown_nodes:
            raise ValueError(f"graph nodes are not rooms: {unknown_nodes}")
        nodes = set(self.graph.nodes)
        for edge in self.graph.edges:
            if edge.opening_id not in opening_ids:
                raise ValueError(f"graph edge refers to unknown opening {edge.opening_id}")
            if edge.a not in nodes or edge.b not in nodes:
                raise ValueError(f"graph edge {edge.opening_id}: endpoints must be graph nodes")

    def wall(self, wall_id: str) -> Wall:
        return next(w for w in self.walls if w.id == wall_id)

    def opening(self, opening_id: str) -> Opening:
        return next(o for o in self.openings if o.id == opening_id)

    def room(self, room_id: str) -> Room:
        return next(r for r in self.rooms if r.id == room_id)
