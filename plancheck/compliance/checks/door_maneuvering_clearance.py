"""Maneuvering clearance at a swinging door, front approach (serves 2010 ADA 404.2.4.1).

On each side of the door a rectangle of floor must be free of walls and fixtures:

- **pull side** (the side the door swings to): the full doorway width plus a strip beyond
  the latch, to a depth perpendicular to the doorway;
- **push side**: the full doorway width, to a smaller depth.

The check measures how deep the free floor is in front of the doorway and how far it
reaches beyond the latch, and compares each with the rule. It can only prove failure:
furniture and casework are not on the plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from plancheck.compliance.context import CheckContext, geometry_sigma
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, all_of, decide_min
from plancheck.model.geometry import door_swing, opening_span, wall_footprint
from plancheck.model.types import BuildingModel, Measured, Opening, Point

_PROBE_MM = 5000.0  # how far out to look for obstructions
_SKIN_MM = 1.0  # keeps the door's own wall faces from counting as obstructions


def _rect(origin: Point, along: Point, out: Point, length: float, depth: float) -> Polygon:
    """Rectangle from ``origin``: ``length`` along ``along`` and ``depth`` along ``out``."""
    ax, ay = along
    ox, oy = out
    return Polygon(
        [
            origin,
            (origin[0] + ax * length, origin[1] + ay * length),
            (origin[0] + ax * length + ox * depth, origin[1] + ay * length + oy * depth),
            (origin[0] + ox * depth, origin[1] + oy * depth),
        ]
    )


def _shift(point: Point, direction: Point, distance: float) -> Point:
    return (point[0] + direction[0] * distance, point[1] + direction[1] * distance)


def _free_extent(area: Polygon, from_line: LineString, obstacles: BaseGeometry) -> float:
    """How far the free floor inside ``area`` extends away from ``from_line``."""
    blocked = obstacles.intersection(area)
    if blocked.is_empty:
        return _PROBE_MM
    return float(min(from_line.distance(blocked), _PROBE_MM))


@dataclass
class _Side:
    name: str
    verdicts: list[Verdict]
    evidence: list[Evidence]
    short: list[str]


def _measure_side(
    name: str,
    origin: Point,
    along: Point,
    out: Point,
    width: float,
    depth_mm: float,
    latch_mm: float,
    obstacles: BaseGeometry,
    sigma: float,
    k: float,
) -> _Side:
    """Free depth in front of the doorway, and free length beyond the latch, on one side."""
    face = LineString([origin, _shift(origin, along, width)])
    cover = width + latch_mm
    probe = _rect(origin, along, out, cover, _PROBE_MM)
    depth = Measured(
        value_mm=_free_extent(probe, face, obstacles), sigma_mm=sigma, source="geometry"
    )
    side = _Side(name, [decide_min(depth, depth_mm, k)], [], [])
    shown = _rect(origin, along, out, cover, depth_mm)
    side.evidence.append(
        Evidence(kind="polygon", points=list(shown.exterior.coords)[:-1], label=f"{name} side")
    )
    if side.verdicts[0] is Verdict.FAIL:
        side.short.append(f"{name}-side depth {depth.value_mm:.0f} mm")
    if latch_mm > 0:
        latch = _shift(origin, along, width)
        latch_line = LineString([latch, _shift(latch, out, depth_mm)])
        strip = _rect(latch, along, out, _PROBE_MM, depth_mm)
        beyond = Measured(
            value_mm=_free_extent(strip, latch_line, obstacles), sigma_mm=sigma, source="geometry"
        )
        side.verdicts.append(decide_min(beyond, latch_mm, k))
        if side.verdicts[1] is Verdict.FAIL:
            side.short.append(f"{name}-side latch clearance {beyond.value_mm:.0f} mm")
    return side


def door_maneuvering_clearance(
    model: BuildingModel, rule: Rule, opening: Opening, ctx: CheckContext
) -> CheckOutcome:
    wall = model.wall(opening.wall_id)
    swing = door_swing(wall, opening)
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]
    if swing is None:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason="hinge side or swing direction not known",
            surfaced_exceptions=surfaced,
        )

    first, second = opening_span(wall, opening)
    hinge_jamb = first if opening.hinge_at == "start" else second
    width = opening.width.value_mm
    half = wall.thickness.value_mm / 2
    pull_out = swing.outward
    push_out = (-pull_out[0], -pull_out[1])
    obstacles = unary_union(
        [wall_footprint(w) for w in model.walls] + [Polygon(f.footprint) for f in model.fixtures]
    ).buffer(-_SKIN_MM)
    sigma = geometry_sigma(model)
    req = rule.requirement

    sides = [
        _measure_side(
            "pull",
            _shift(hinge_jamb, pull_out, half),
            swing.along,
            pull_out,
            width,
            req["pull_perpendicular"].mm,
            req["pull_beyond_latch"].mm,
            obstacles,
            sigma,
            ctx.k,
        ),
        _measure_side(
            "push",
            _shift(hinge_jamb, push_out, half),
            swing.along,
            push_out,
            width,
            req["push_perpendicular"].mm,
            req["push_beyond_latch"].mm,
            obstacles,
            sigma,
            ctx.k,
        ),
    ]
    short = [s for side in sides for s in side.short]
    reason = "front approach assumed; " + (
        f"short on {', '.join(short)}" if short else "clear of walls and modelled fixtures"
    )
    required = (
        f"pull {req['pull_perpendicular'].as_written()} deep + "
        f"{req['pull_beyond_latch'].as_written()} beyond latch; "
        f"push {req['push_perpendicular'].as_written()} deep"
    )
    return CheckOutcome(
        verdict=all_of(v for side in sides for v in side.verdicts),
        required=required,
        reason=reason,
        surfaced_exceptions=surfaced,
        evidence=[e for side in sides for e in side.evidence],
    )
