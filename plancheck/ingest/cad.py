"""Explicit exact-CAD entities. Geometry is read from vectors, never a model sidecar."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from plancheck.model.types import (
    EXTERIOR,
    BuildingModel,
    Dimension,
    Fixture,
    GraphEdge,
    Opening,
    Point,
    ProjectContext,
    Room,
    RoomGraph,
    Wall,
)


class CadEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["wall", "opening", "room", "boundary", "route", "fixture", "dimension"]
    points: list[Point]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _points(self) -> Self:
        minimum = {
            "wall": 2,
            "opening": 1,
            "room": 3,
            "boundary": 3,
            "route": 2,
            "fixture": 3,
            "dimension": 2,
        }[self.kind]
        if self.kind in ("wall", "opening", "dimension") and len(self.points) != minimum:
            raise ValueError(f"{self.kind} needs exactly {minimum} vector points")
        if len(self.points) < minimum:
            raise ValueError(f"{self.kind} needs at least {minimum} vector points")
        return self


def model_entities(model: BuildingModel) -> list[CadEntity]:
    result = []
    for w in model.walls:
        result.append(
            CadEntity(
                kind="wall",
                points=[w.start, w.end],
                metadata=w.model_dump(exclude={"start", "end"}),
            )
        )
    for o in model.openings:
        edges = [e for e in model.graph.edges if e.opening_id == o.id]
        if len(edges) > 1:
            raise ValueError("exact CAD supports one room-graph connection per opening")
        data = o.model_dump(exclude={"position_along_wall_mm"})
        data["connects"] = [edges[0].a, edges[0].b] if edges else []
        result.append(
            CadEntity(
                kind="opening",
                points=[model.wall(o.wall_id).point_at(o.position_along_wall_mm)],
                metadata=data,
            )
        )
    for r in model.rooms:
        data = r.model_dump(
            exclude={"boundary", "clear_polygon", "corridor_paths", "area_net_m2", "area_gross_m2"}
        )
        result.extend(
            [
                CadEntity(kind="room", points=r.clear_polygon, metadata=data),
                CadEntity(kind="boundary", points=r.boundary, metadata={"id": r.id}),
            ]
        )
        result.extend(
            CadEntity(kind="route", points=path, metadata={"room_id": r.id})
            for path in r.corridor_paths
        )
    result.extend(
        CadEntity(kind="fixture", points=f.footprint, metadata=f.model_dump(exclude={"footprint"}))
        for f in model.fixtures
    )
    result.extend(
        CadEntity(
            kind="dimension", points=[d.p1, d.p2], metadata=d.model_dump(exclude={"p1", "p2"})
        )
        for d in model.dimensions
    )
    return result


def entities_model(
    entities: list[CadEntity], project: ProjectContext | None = None
) -> BuildingModel:
    if not entities or not any(e.kind == "wall" for e in entities):
        raise ValueError(
            "no supported exact wall entities; untagged/raster extraction is not implemented"
        )
    walls = [
        Wall.model_validate(
            e.metadata | {"start": e.points[0], "end": e.points[1], "provenance": "vector_import"}
        )
        for e in entities
        if e.kind == "wall"
    ]
    by_wall = {w.id: w for w in walls}
    openings = []
    edges = []
    for e in entities:
        if e.kind != "opening":
            continue
        data = dict(e.metadata)
        connected = data.pop("connects", [])
        wall = by_wall[data["wall_id"]]
        dx, dy = wall.direction
        x, y = e.points[0][0] - wall.start[0], e.points[0][1] - wall.start[1]
        if abs(x * dy - y * dx) > 1e-3:
            raise ValueError(f"opening {data['id']} locator is not on its host wall axis")
        openings.append(
            Opening.model_validate(
                data | {"position_along_wall_mm": x * dx + y * dy, "provenance": "vector_import"}
            )
        )
        if connected:
            if len(connected) != 2:
                raise ValueError("connects must contain two room/exterior IDs")
            edges.append(GraphEdge(opening_id=data["id"], a=connected[0], b=connected[1]))
    boundaries = {e.metadata["id"]: e.points for e in entities if e.kind == "boundary"}
    rooms = [
        Room.model_validate(
            e.metadata
            | {
                "clear_polygon": e.points,
                "boundary": boundaries[e.metadata["id"]],
                "corridor_paths": [
                    p.points
                    for p in entities
                    if p.kind == "route" and p.metadata["room_id"] == e.metadata["id"]
                ],
                "provenance": "vector_import",
            }
        )
        for e in entities
        if e.kind == "room"
    ]
    fixtures = [
        Fixture.model_validate(e.metadata | {"footprint": e.points, "provenance": "vector_import"})
        for e in entities
        if e.kind == "fixture"
    ]
    dimensions = [
        Dimension.model_validate(
            e.metadata | {"p1": e.points[0], "p2": e.points[1], "provenance": "vector_import"}
        )
        for e in entities
        if e.kind == "dimension"
    ]
    return BuildingModel(
        walls=walls,
        openings=openings,
        rooms=rooms,
        fixtures=fixtures,
        dimensions=dimensions,
        project=project or ProjectContext(),
        graph=RoomGraph(nodes=[r.id for r in rooms] + [EXTERIOR], edges=edges),
        scale_source="exact",
        scale_rel_sigma=0,
    )
