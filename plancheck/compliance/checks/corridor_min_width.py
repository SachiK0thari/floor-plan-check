"""Event-exact transverse width profiles for rectilinear corridors.

See docs/corridor_width.md for the supported geometry and route contract.
"""

from __future__ import annotations

import math
from itertools import pairwise

from pydantic import BaseModel, ConfigDict
from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon
from shapely.geometry import Point as SPoint
from shapely.ops import unary_union

from plancheck.compliance.checks.turning_space import free_area
from plancheck.compliance.context import CheckContext, geometry_sigma
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, all_of, decide_max, decide_min
from plancheck.model.types import BuildingModel, Measured, Point, Room

TOL = 1e-6


class WidthInterval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start_mm: float
    end_mm: float
    width_mm: float
    section: list[Point]
    segment: int


def _profile(floor: Polygon, path: list[Point]) -> list[WidthInterval]:
    if len(path) < 2:
        raise ValueError("corridor path needs at least two points")
    if not floor.buffer(TOL).covers(LineString(path)):
        raise ValueError("corridor path must lie inside the free floor")
    out = []
    offset = 0.0
    for index, (a, b) in enumerate(pairwise(path)):
        length = math.dist(a, b)
        if length <= TOL:
            raise ValueError("corridor path contains a zero-length segment")
        angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        local = rotate(floor, -angle, origin=a)
        rings = [local.exterior, *local.interiors]
        for ring in rings:
            for p, q in pairwise(ring.coords):
                if abs(p[0] - q[0]) > TOL and abs(p[1] - q[1]) > TOL:
                    raise ValueError("corridor requires rectilinear floor and orthogonal paths")
        events = sorted(
            {
                0.0,
                length,
                *(
                    float(p[0] - a[0])
                    for ring in rings
                    for p in ring.coords
                    if TOL < p[0] - a[0] < length - TOL
                ),
            }
        )
        low, high = local.bounds[1] - 1, local.bounds[3] + 1
        for lo, hi in pairwise(events):
            if hi - lo <= TOL:
                continue
            x = a[0] + (lo + hi) / 2
            cut = local.intersection(LineString([(x, low), (x, high)]))
            lines = [cut] if cut.geom_type == "LineString" else list(cut.geoms)
            hits = [
                line
                for line in lines
                if line.geom_type == "LineString" and line.distance(SPoint(x, a[1])) < TOL
            ]
            if len(hits) != 1 or hits[0].length <= TOL:
                raise ValueError("corridor path has an ambiguous transverse section")
            section = rotate(hits[0], angle, origin=a)
            out.append(
                WidthInterval(
                    start_mm=offset + lo,
                    end_mm=offset + hi,
                    width_mm=hits[0].length,
                    section=list(section.coords),
                    segment=index,
                )
            )
        offset += length
    return out


def corridor_min_width(
    model: BuildingModel, rule: Rule, room: Room, ctx: CheckContext
) -> CheckOutcome:
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]
    required = rule.requirement["min_clear_width"]
    floor = free_area(model, room)
    if not isinstance(floor, Polygon) or floor.is_empty:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason="connected clear floor is required",
            surfaced_exceptions=surfaced,
        )
    paths = room.corridor_paths
    if not paths:
        rectangle = floor.minimum_rotated_rectangle
        if floor.interiors or floor.symmetric_difference(rectangle).area > TOL:
            return CheckOutcome(
                verdict=Verdict.UNKNOWN,
                reason="corridor_paths required for non-rectangular corridors",
                surfaced_exceptions=surfaced,
            )
        corners = list(rectangle.exterior.coords)
        edges = list(pairwise(corners))
        short = min(range(4), key=lambda i: math.dist(*edges[i]))
        a, b = edges[short]
        c, d = edges[(short + 2) % 4]
        paths = [[((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)]]
    try:
        profiles = [_profile(floor, path) for path in paths]
        rectangle = floor.minimum_rotated_rectangle
        if not floor.interiors and floor.symmetric_difference(rectangle).area <= TOL:
            short_side = min(math.dist(a, b) for a, b in pairwise(rectangle.exterior.coords))
            if min(i.width_mm for p in profiles for i in p) > short_side + TOL:
                raise ValueError(
                    "rectangular corridor paths must follow the longitudinal direction"
                )
        for profile in profiles:
            for interval in profile:
                if (
                    interval.width_mm > min(i.width_mm for i in profile) + TOL
                    and interval.width_mm > interval.end_mm - interval.start_mm
                ):
                    section = LineString(interval.section)
                    if not any(
                        section.buffer((interval.end_mm - interval.start_mm) / 2 + TOL, cap_style=2)
                        .intersection(LineString(path))
                        .length
                        > interval.width_mm / 2
                        for path in paths
                    ):
                        raise ValueError("wide transverse branch requires its own corridor path")
        # Sweep each measured section over its entire constant-width event interval.
        # Their union must cover the floor: an omitted arm or truncated route is unknown.
        swept = []
        for path, profile in zip(paths, profiles, strict=True):
            for interval in profile:
                a, b = path[interval.segment : interval.segment + 2]
                length = math.dist(a, b)
                half = (interval.end_mm - interval.start_mm) / 2
                dx, dy = (b[0] - a[0]) / length * half, (b[1] - a[1]) / length * half
                p, q = interval.section[0], interval.section[-1]
                swept.append(
                    Polygon(
                        [
                            (p[0] - dx, p[1] - dy),
                            (q[0] - dx, q[1] - dy),
                            (q[0] + dx, q[1] + dy),
                            (p[0] + dx, p[1] + dy),
                        ]
                    )
                )
        if floor.difference(unary_union(swept)).area > TOL:
            raise ValueError("corridor_paths must cover every corridor arm and its full length")
    except ValueError as exc:
        return CheckOutcome(verdict=Verdict.UNKNOWN, reason=str(exc), surfaced_exceptions=surfaced)
    sigma = 2 * geometry_sigma(model)

    def measured(value: float) -> Measured:
        return Measured(
            value_mm=value,
            sigma_mm=math.hypot(sigma, value * (model.scale_rel_sigma or 0)),
            source="geometry",
        )

    intervals = [i for profile in profiles for i in profile]
    minimum = min(intervals, key=lambda i: i.width_mm)
    evidence = [
        Evidence(
            kind="line",
            points=i.section,
            label=f"width {i.width_mm:g} mm; station {i.start_mm:g}-{i.end_mm:g} mm",
        )
        for i in intervals
        if i.width_mm < required.mm + ctx.k * measured(i.width_mm).sigma_mm
    ]
    if not evidence:
        evidence = [Evidence(kind="line", points=minimum.section, label="minimum corridor width")]
    exception = next(
        (e for e in rule.exceptions if e.id == "short-reduction" and e.handling == "checked"), None
    )
    verdicts = []
    notes = []
    for profile in profiles:
        runs: list[list[WidthInterval]] = []
        uncertain_membership = False
        for interval in profile:
            base = decide_min(measured(interval.width_mm), required.mm, ctx.k)
            uncertain_membership |= base is Verdict.BORDERLINE
            if interval.width_mm < required.mm - TOL:
                if runs and abs(runs[-1][-1].end_mm - interval.start_mm) < TOL:
                    runs[-1].append(interval)
                else:
                    runs.append([interval])
        if not runs:
            verdicts.append(
                all_of(decide_min(measured(i.width_mm), required.mm, ctx.k) for i in profile)
            )
            continue
        if exception is None:
            verdicts.append(
                all_of(decide_min(measured(i.width_mm), required.mm, ctx.k) for i in profile)
            )
            continue
        params = exception.params
        widths = all_of(
            decide_min(measured(i.width_mm), params["reduced_width"].mm, ctx.k)
            for run in runs
            for i in run
        )
        if len(paths) > 1 or any(len({i.segment for i in run}) > 1 for run in runs):
            verdicts.append(all_of([widths, Verdict.UNKNOWN]))
            notes.append("short-reduction distances across branches/bends require review")
            continue
        conditions = [widths]
        for run in runs:
            length = run[-1].end_mm - run[0].start_mm
            notes.append(f"narrow run {length:g} mm")
            conditions.append(decide_max(measured(length), params["max_length"].mm, ctx.k))
        for first, second in pairwise(runs):
            gap = second[0].start_mm - first[-1].end_mm
            notes.append(f"separation {gap:g} mm")
            conditions.append(decide_min(measured(gap), params["separation_length"].mm, ctx.k))
            conditions.extend(
                decide_min(measured(i.width_mm), params["separation_width"].mm, ctx.k)
                for i in profile
                if first[-1].end_mm <= i.start_mm < second[0].start_mm
            )
        # Uncertain threshold membership changes run topology. Avoid a definite verdict
        # based on nominal grouping; a definite sub-minimum width still proves failure.
        verdicts.append(
            all_of([widths, Verdict.BORDERLINE]) if uncertain_membership else all_of(conditions)
        )
    return CheckOutcome(
        verdict=all_of(verdicts),
        measured=measured(minimum.width_mm),
        required=required.as_written(),
        required_mm=required.mm,
        reason="event-exact transverse width profile; " + "; ".join(notes),
        surfaced_exceptions=surfaced,
        evidence=evidence,
    )
