"""Random rectangular floor plans with exact ground truth.

For unit tests and early pipeline testing only. The generator and the pipeline share
assumptions (straight walls, right angles, one door symbol), so results on these plans
overstate accuracy and never go into headline numbers (docs/PROJECT_SPEC.md §7.3).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from plancheck import __version__
from plancheck.config import load_config
from plancheck.model.types import (
    EXTERIOR,
    BuildingModel,
    GraphEdge,
    Measured,
    Opening,
    Point,
    Room,
    RoomGraph,
    Wall,
)

_MM_PER_UNIT = {"mm": 1.0, "in": 25.4}
_LABELS = ("OFFICE", "MEETING", "RECEPTION", "STORAGE", "BREAK ROOM", "TOILET")
_MAX_ATTEMPTS = 50

Rect = tuple[int, int, int, int]  # x0, y0, x1, y1 in mm


def catalog_leaf_widths_mm(catalog: str = "us_nominal") -> tuple[float, ...]:
    """Door leaf widths from ``configs/door_catalog.yaml``, converted to millimetres."""
    entry = load_config("door_catalog")[catalog]
    factor = _MM_PER_UNIT[entry["unit"]]
    return tuple(float(width) * factor for width in entry["leaf_widths"])


@dataclass(frozen=True)
class SyntheticConfig:
    """Drawing parameters for generated plans. None of these are code requirements."""

    min_width_mm: int = 8000
    max_width_mm: int = 16000
    min_depth_mm: int = 6000
    max_depth_mm: int = 12000
    grid_mm: int = 100
    min_room_mm: int = 2400
    max_rooms: int = 8
    exterior_thickness_mm: float = 200.0
    interior_thickness_mm: float = 100.0
    leaf_widths_mm: tuple[float, ...] | None = None  # None: read the door catalog
    frame_allowance_mm: float = 50.0  # gap in the wall = leaf width + this
    edge_margin_mm: float = 150.0  # clear distance from an opening to anything else
    extra_door_prob: float = 0.2
    second_exterior_door_prob: float = 0.3
    window_prob: float = 0.6
    window_widths_mm: tuple[float, ...] = (600.0, 900.0, 1200.0, 1500.0, 1800.0)


@dataclass(frozen=True)
class _WallRef:
    """A generated wall plus the axis-aligned interval it covers."""

    wall: Wall
    axis: str  # "v": constant x, "h": constant y
    coord: int
    lo: int
    hi: int


@dataclass(frozen=True)
class _Edge:
    """A stretch of wall with a room on one side and a room or the exterior on the other."""

    axis: str
    coord: int
    lo: int
    hi: int
    a: str
    b: str


class _Layout:
    """Mutable state while openings are being placed."""

    def __init__(self, cfg: SyntheticConfig, rng: random.Random, walls: list[_WallRef]) -> None:
        self.cfg = cfg
        self.rng = rng
        self.walls = walls
        self.taken: dict[str, list[tuple[float, float]]] = {}
        self.openings: list[Opening] = []
        self.edges: list[GraphEdge] = []

    def _wall_for(self, edge: _Edge) -> _WallRef:
        return next(
            w
            for w in self.walls
            if w.axis == edge.axis and w.coord == edge.coord and w.lo <= edge.lo and edge.hi <= w.hi
        )

    def _free_centre(self, ref: _WallRef, edge: _Edge, gap: float) -> float | None:
        """A centre for a gap of this width on the edge, clear of corners and other openings."""
        margin = self.cfg.edge_margin_mm + self.cfg.exterior_thickness_mm / 2
        lo = math.ceil(edge.lo + margin + gap / 2)
        hi = math.floor(edge.hi - margin - gap / 2)
        if hi < lo:
            return None
        for _ in range(20):
            centre = float(self.rng.randint(lo, hi))
            span = (centre - gap / 2, centre + gap / 2)
            clear = self.cfg.edge_margin_mm
            if all(
                span[1] + clear <= t0 or t1 + clear <= span[0]
                for t0, t1 in self.taken.get(ref.wall.id, [])
            ):
                self.taken.setdefault(ref.wall.id, []).append(span)
                return centre
        return None

    def _position(self, ref: _WallRef, centre: float) -> float:
        point = (ref.coord, centre) if ref.axis == "v" else (centre, ref.coord)
        return math.dist(ref.wall.start, point)

    def place_door(self, edge: _Edge) -> bool:
        ref = self._wall_for(edge)
        leaves = list(self.cfg.leaf_widths_mm or catalog_leaf_widths_mm())
        self.rng.shuffle(leaves)
        for leaf in leaves:
            gap = leaf + self.cfg.frame_allowance_mm
            centre = self._free_centre(ref, edge, gap)
            if centre is None:
                continue
            number = sum(o.kind == "door" for o in self.openings) + 1
            door = Opening(
                id=f"D{number:02d}",
                kind="door",
                wall_id=ref.wall.id,
                position_along_wall_mm=self._position(ref, centre),
                width=Measured(value_mm=gap, sigma_mm=0.0, source="geometry"),
                leaf_width=Measured(value_mm=leaf, sigma_mm=0.0, source="nominal_snap"),
                operation="swing",
                hinge_at=self.rng.choice(("start", "end")),
                swings_to=self.rng.choice(("left", "right")),
                tag=f"{number:02d}",
                provenance="synthetic",
            )
            self.openings.append(door)
            self.edges.append(GraphEdge(opening_id=door.id, a=edge.a, b=edge.b))
            return True
        return False

    def place_window(self, edge: _Edge) -> bool:
        ref = self._wall_for(edge)
        widths = list(self.cfg.window_widths_mm)
        self.rng.shuffle(widths)
        for width in widths:
            centre = self._free_centre(ref, edge, width)
            if centre is None:
                continue
            number = sum(o.kind == "window" for o in self.openings) + 1
            self.openings.append(
                Opening(
                    id=f"WIN{number:02d}",
                    kind="window",
                    wall_id=ref.wall.id,
                    position_along_wall_mm=self._position(ref, centre),
                    width=Measured(value_mm=width, sigma_mm=0.0, source="geometry"),
                    provenance="synthetic",
                )
            )
            return True
        return False


def _split(
    rng: random.Random, cfg: SyntheticConfig, width: int, depth: int
) -> tuple[list[Rect], list[tuple[str, int, int, int]]]:
    """Cut the outline into rooms with straight cuts. Returns rooms and the cut lines."""
    rects: list[Rect] = [(0, 0, width, depth)]
    cuts: list[tuple[str, int, int, int]] = []
    target = rng.randint(2, cfg.max_rooms)
    need = 2 * cfg.min_room_mm
    while len(rects) < target:
        splittable = [r for r in rects if r[2] - r[0] >= need or r[3] - r[1] >= need]
        if not splittable:
            break
        rect = max(splittable, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        x0, y0, x1, y1 = rect
        w, d = x1 - x0, y1 - y0
        vertical = w >= need and (w >= d or d < need)
        rects.remove(rect)
        if vertical:
            x = rng.randrange(x0 + cfg.min_room_mm, x1 - cfg.min_room_mm + 1, cfg.grid_mm)
            rects += [(x0, y0, x, y1), (x, y0, x1, y1)]
            cuts.append(("v", x, y0, y1))
        else:
            y = rng.randrange(y0 + cfg.min_room_mm, y1 - cfg.min_room_mm + 1, cfg.grid_mm)
            rects += [(x0, y0, x1, y), (x0, y, x1, y1)]
            cuts.append(("h", y, x0, x1))
    return rects, cuts


def _walls(
    cfg: SyntheticConfig, width: int, depth: int, cuts: list[tuple[str, int, int, int]]
) -> list[_WallRef]:
    def make(index: int, start: Point, end: Point, exterior: bool) -> Wall:
        thickness = cfg.exterior_thickness_mm if exterior else cfg.interior_thickness_mm
        return Wall(
            id=f"W{index:02d}",
            start=start,
            end=end,
            thickness=Measured(value_mm=thickness, sigma_mm=0.0, source="geometry"),
            is_exterior=exterior,
            provenance="synthetic",
        )

    w, d = float(width), float(depth)
    # Exterior walls run counter-clockwise, so their left side faces into the building.
    refs = [
        _WallRef(make(1, (0.0, 0.0), (w, 0.0), True), "h", 0, 0, width),
        _WallRef(make(2, (w, 0.0), (w, d), True), "v", width, 0, depth),
        _WallRef(make(3, (w, d), (0.0, d), True), "h", depth, 0, width),
        _WallRef(make(4, (0.0, d), (0.0, 0.0), True), "v", 0, 0, depth),
    ]
    for offset, (axis, coord, lo, hi) in enumerate(cuts):
        c, a, b = float(coord), float(lo), float(hi)
        start, end = ((c, a), (c, b)) if axis == "v" else ((a, c), (b, c))
        refs.append(_WallRef(make(5 + offset, start, end, False), axis, coord, lo, hi))
    return refs


def _rooms(
    rng: random.Random, cfg: SyntheticConfig, rects: list[Rect], width: int, depth: int
) -> list[Room]:
    type_map = load_config("room_type_map")
    half_ext, half_int = cfg.exterior_thickness_mm / 2, cfg.interior_thickness_mm / 2
    rooms = []
    for index, (x0, y0, x1, y1) in enumerate(rects, start=1):
        left = x0 + (half_ext if x0 == 0 else half_int)
        right = x1 - (half_ext if x1 == width else half_int)
        bottom = y0 + (half_ext if y0 == 0 else half_int)
        top = y1 - (half_ext if y1 == depth else half_int)
        label = rng.choice(_LABELS)
        rooms.append(
            Room(
                id=f"R{index:02d}",
                boundary=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                clear_polygon=[(left, bottom), (right, bottom), (right, top), (left, top)],
                label=label,
                room_type=type_map.get(label),
                provenance="synthetic",
            )
        )
    return rooms


def _shared_edges(rects: list[Rect], rooms: list[Room]) -> list[_Edge]:
    edges = []
    for i, a in enumerate(rects):
        for j in range(i + 1, len(rects)):
            b = rects[j]
            if a[2] == b[0] or b[2] == a[0]:
                x = a[2] if a[2] == b[0] else a[0]
                lo, hi = max(a[1], b[1]), min(a[3], b[3])
                if hi > lo:
                    edges.append(_Edge("v", x, lo, hi, rooms[i].id, rooms[j].id))
            if a[3] == b[1] or b[3] == a[1]:
                y = a[3] if a[3] == b[1] else a[1]
                lo, hi = max(a[0], b[0]), min(a[2], b[2])
                if hi > lo:
                    edges.append(_Edge("h", y, lo, hi, rooms[i].id, rooms[j].id))
    return edges


def _exterior_edges(rects: list[Rect], rooms: list[Room], width: int, depth: int) -> list[_Edge]:
    edges = []
    for (x0, y0, x1, y1), room in zip(rects, rooms, strict=True):
        if y0 == 0:
            edges.append(_Edge("h", 0, x0, x1, room.id, EXTERIOR))
        if x1 == width:
            edges.append(_Edge("v", width, y0, y1, room.id, EXTERIOR))
        if y1 == depth:
            edges.append(_Edge("h", depth, x0, x1, room.id, EXTERIOR))
        if x0 == 0:
            edges.append(_Edge("v", 0, y0, y1, room.id, EXTERIOR))
    return edges


def _attempt(rng: random.Random, cfg: SyntheticConfig) -> BuildingModel | None:
    width = rng.randrange(cfg.min_width_mm, cfg.max_width_mm + 1, cfg.grid_mm)
    depth = rng.randrange(cfg.min_depth_mm, cfg.max_depth_mm + 1, cfg.grid_mm)
    rects, cuts = _split(rng, cfg, width, depth)
    wall_refs = _walls(cfg, width, depth, cuts)
    rooms = _rooms(rng, cfg, rects, width, depth)
    layout = _Layout(cfg, rng, wall_refs)

    # Interior doors: first enough to connect every room, then a few extra.
    shared = _shared_edges(rects, rooms)
    rng.shuffle(shared)
    group = {room.id: room.id for room in rooms}

    def find(room_id: str) -> str:
        while group[room_id] != room_id:
            room_id = group[room_id]
        return room_id

    spare = []
    for edge in shared:
        if find(edge.a) != find(edge.b) and layout.place_door(edge):
            group[find(edge.a)] = find(edge.b)
        else:
            spare.append(edge)
    if len({find(room.id) for room in rooms}) > 1:
        return None
    for edge in spare:
        if rng.random() < cfg.extra_door_prob:
            layout.place_door(edge)

    # Exterior doors, then windows.
    exterior = _exterior_edges(rects, rooms, width, depth)
    rng.shuffle(exterior)
    wanted = 2 if rng.random() < cfg.second_exterior_door_prob else 1
    remaining = []
    for edge in exterior:
        if wanted and layout.place_door(edge):
            wanted -= 1
        else:
            remaining.append(edge)
    if not any(edge.b == EXTERIOR for edge in layout.edges):
        return None
    for edge in remaining:
        if rng.random() < cfg.window_prob:
            layout.place_window(edge)

    return BuildingModel(
        walls=[ref.wall for ref in wall_refs],
        openings=layout.openings,
        rooms=rooms,
        graph=RoomGraph(nodes=[room.id for room in rooms] + [EXTERIOR], edges=layout.edges),
        model_versions={"synthetic_generator": __version__},
    )


def generate_model(seed: int, cfg: SyntheticConfig | None = None) -> BuildingModel:
    """A random plan. The same seed and config always give the same plan.

    Every room is reachable from the exterior through doors.
    """
    cfg = cfg or SyntheticConfig()
    for attempt in range(_MAX_ATTEMPTS):
        model = _attempt(random.Random(f"{seed}:{attempt}"), cfg)
        if model is not None:
            return model
    raise RuntimeError(f"no connected plan found for seed {seed} in {_MAX_ATTEMPTS} attempts")
