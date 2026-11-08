"""Geometry derived from a BuildingModel. Shared by the exporters and the renderer.

Everything here is in plan millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from plancheck.model.types import BuildingModel, Opening, OpeningKind, Point, Wall

_CUT_OVERSHOOT_MM = 1.0
"""How far a gap rectangle sticks out past each wall face, so the cut is clean."""


def wall_footprint(wall: Wall) -> Polygon:
    """The wall's area on plan: its centerline widened to the wall thickness.

    Ends are squared off half a thickness past the endpoints, so two walls that meet at a
    corner fill the corner instead of leaving a notch.
    """
    line = LineString([wall.start, wall.end])
    return line.buffer(wall.thickness.value_mm / 2, cap_style="square", join_style="mitre")


def opening_span(wall: Wall, opening: Opening) -> tuple[Point, Point]:
    """The two ends of the opening on the wall centerline, in wall direction order."""
    half = opening.width.value_mm / 2
    return (
        wall.point_at(opening.position_along_wall_mm - half),
        wall.point_at(opening.position_along_wall_mm + half),
    )


def opening_gap(wall: Wall, opening: Opening) -> Polygon:
    """Rectangle covering the opening through the full wall thickness (plus a small overshoot)."""
    p1, p2 = opening_span(wall, opening)
    half = wall.thickness.value_mm / 2 + _CUT_OVERSHOOT_MM
    return LineString([p1, p2]).buffer(half, cap_style="flat")


def polygons(geometry: BaseGeometry) -> list[Polygon]:
    """The polygon parts of a geometry, as a list."""
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, Polygon)]


def wall_solids(
    model: BuildingModel, cut: tuple[OpeningKind, ...] = ("door", "window", "opening")
) -> list[Polygon]:
    """Wall area on plan as polygons, with the given kinds of openings cut out."""
    walls = {wall.id: wall for wall in model.walls}
    solid = unary_union([wall_footprint(wall) for wall in model.walls])
    gaps = [opening_gap(walls[o.wall_id], o) for o in model.openings if o.kind in cut]
    if gaps:
        solid = solid.difference(unary_union(gaps))
    return polygons(solid)


@dataclass(frozen=True)
class DoorSwing:
    """Where a swing door's leaf sits, on plan.

    ``hinge`` is the pivot, on the wall face of the side the door opens to. ``latch`` is
    the free edge of the leaf when closed; ``tip`` is the free edge when open 90°.
    ``along`` and ``outward`` are unit vectors from the hinge towards the latch and
    towards the tip. The leaf length is the distance from hinge to either.
    """

    hinge: Point
    latch: Point
    tip: Point
    along: Point
    outward: Point
    leaf_mm: float


def door_swing(wall: Wall, opening: Opening) -> DoorSwing | None:
    """Swing geometry for a door, or None if its hinge end or swing side is not known."""
    if opening.kind != "door" or opening.hinge_at is None or opening.swings_to is None:
        return None
    first, second = opening_span(wall, opening)
    dx, dy = wall.direction
    if opening.hinge_at == "start":
        base, along = first, (dx, dy)
    else:
        base, along = second, (-dx, -dy)
    nx, ny = wall.left_normal
    outward = (nx, ny) if opening.swings_to == "left" else (-nx, -ny)
    half = wall.thickness.value_mm / 2
    hinge = (base[0] + outward[0] * half, base[1] + outward[1] * half)
    leaf = (opening.leaf_width or opening.width).value_mm
    return DoorSwing(
        hinge=hinge,
        latch=(hinge[0] + along[0] * leaf, hinge[1] + along[1] * leaf),
        tip=(hinge[0] + outward[0] * leaf, hinge[1] + outward[1] * leaf),
        along=along,
        outward=outward,
        leaf_mm=leaf,
    )


def model_bounds(model: BuildingModel) -> tuple[float, float, float, float]:
    """(min x, min y, max x, max y) of the wall footprints."""
    if not model.walls:
        raise ValueError("model has no walls")
    minx, miny, maxx, maxy = unary_union([wall_footprint(w) for w in model.walls]).bounds
    return (float(minx), float(miny), float(maxx), float(maxy))


def drawing_bounds(model: BuildingModel) -> tuple[float, float, float, float]:
    """(min x, min y, max x, max y) of everything that gets drawn: walls and door swings.

    A door that opens outwards reaches past the wall faces, so this can be larger than
    ``model_bounds``.
    """
    minx, miny, maxx, maxy = model_bounds(model)
    walls = {wall.id: wall for wall in model.walls}
    for opening in model.openings:
        swing = door_swing(walls[opening.wall_id], opening)
        if swing is not None:
            for x, y in (swing.hinge, swing.latch, swing.tip):
                minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x), max(maxy, y)
    return (minx, miny, maxx, maxy)
