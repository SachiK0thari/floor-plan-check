"""Turning space in a room (serves 2010 ADA 603.2.1 via 304.3).

A room passes if either shape fits in its clear floor area:

- a **circle** of the required diameter, found exactly with the maximum inscribed circle;
- a **T** inside a square of the required size, with arms and base of the required width,
  found on a 10 mm grid by testing every position of the T in four orientations.

Door swings may overlap the turning space (304.4), so they are not subtracted. Modelled
fixtures are. Unmodelled fixtures and casework are why the check can only prove failure.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from plancheck.compliance.context import CheckContext, geometry_sigma
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, any_of, decide_min
from plancheck.model.types import BuildingModel, Measured, Room

CELL_MM = 10.0


def free_area(model: BuildingModel, room: Room) -> Polygon | BaseGeometry:
    """The room's clear floor area less any modelled fixtures."""
    floor: BaseGeometry = Polygon(room.clear_polygon)
    footprints = [Polygon(f.footprint) for f in model.fixtures if f.room_id == room.id]
    if footprints:
        floor = floor.difference(unary_union(footprints))
    return floor


def largest_circle(floor: BaseGeometry) -> tuple[float, tuple[float, float]]:
    """Diameter and centre of the largest circle that fits."""
    if floor.is_empty:
        return 0.0, (0.0, 0.0)
    radius_line = shapely.maximum_inscribed_circle(floor, tolerance=0.5)
    (cx, cy), (bx, by) = radius_line.coords
    return 2 * math.dist((cx, cy), (bx, by)), (cx, cy)


def _free_cells(floor: BaseGeometry, cell: float) -> tuple[np.ndarray, tuple[float, float]]:
    """Grid of cells that lie entirely inside ``floor``, and the grid origin."""
    minx, miny, maxx, maxy = floor.bounds
    cols, rows = int((maxx - minx) // cell) + 1, int((maxy - miny) // cell) + 1
    xs = minx + (np.arange(cols) + 0.5) * cell
    ys = miny + (np.arange(rows) + 0.5) * cell
    gx, gy = np.meshgrid(xs, ys)
    # A cell is free only if its whole square is inside: shrink the floor by half a diagonal.
    inner = floor.buffer(-cell * math.sqrt(0.5))
    free = shapely.contains_xy(inner, gx.ravel(), gy.ravel()).reshape(rows, cols)
    return free, (minx, miny)


def _window_fits(free: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """For each top-left cell, whether an all-free ``rows`` x ``cols`` window starts there."""
    out = np.zeros_like(free)
    if rows > free.shape[0] or cols > free.shape[1] or rows <= 0 or cols <= 0:
        return out
    padded = np.pad(free.astype(np.int32), ((1, 0), (1, 0)))
    sums = padded.cumsum(0).cumsum(1)
    total = sums[rows:, cols:] - sums[:-rows, cols:] - sums[rows:, :-cols] + sums[:-rows, :-cols]
    out[: free.shape[0] - rows + 1, : free.shape[1] - cols + 1] = total == rows * cols
    return out


def t_fits(
    floor: BaseGeometry, square_mm: float, width_mm: float, cell: float = CELL_MM
) -> tuple[float, float] | None:
    """Where a T-shaped space fits, or None.

    The T is a bar ``square`` long and ``width`` wide, with a stem ``width`` wide reaching
    the far side of the square. Returns the centre of the square it was found in.
    """
    if floor.is_empty:
        return None
    free, (ox, oy) = _free_cells(floor, cell)
    square, width = math.ceil(square_mm / cell), math.ceil(width_mm / cell)
    stem_len, offset = square - width, (square - width) // 2
    if stem_len <= 0:
        return None
    for orientation in range(4):
        grid = np.rot90(free, orientation)
        bar = _window_fits(grid, width, square)  # bar across the top of the square
        stem = _window_fits(grid, stem_len, width)  # stem hanging below its middle
        r, c = grid.shape
        hits = np.zeros_like(grid)
        if r > width and c > offset:
            # Stem top-left is `width` rows below and `offset` columns right of the bar's.
            hits[: r - width, : c - offset] = bar[: r - width, : c - offset] & stem[width:, offset:]
        where = np.argwhere(hits)
        if len(where):
            # Mark the square's cells in the rotated frame, rotate back, take their centre.
            i, j = (int(v) for v in where[0])
            cells = np.zeros_like(grid)
            cells[i : i + square, j : j + square] = True
            ii, jj = np.nonzero(np.rot90(cells, -orientation))
            return (float(ox + (jj.mean() + 0.5) * cell), float(oy + (ii.mean() + 0.5) * cell))
    return None


def _circle(centre: tuple[float, float], diameter: float) -> Evidence:
    ring = shapely.Point(centre).buffer(diameter / 2)
    return Evidence(kind="polygon", points=list(ring.exterior.coords)[:-1], label="turning circle")


def turning_space(model: BuildingModel, rule: Rule, room: Room, ctx: CheckContext) -> CheckOutcome:
    req = rule.requirement
    floor = free_area(model, room)
    sigma = math.hypot(geometry_sigma(model), 0.5)  # plus the circle's search tolerance
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]
    fixtures = [f for f in model.fixtures if f.room_id == room.id]

    diameter, centre = largest_circle(floor)
    measured = Measured(value_mm=diameter, sigma_mm=sigma, source="geometry")
    circle_verdict = decide_min(measured, req["circle_diameter"].mm, ctx.k)
    evidence = [_circle(centre, diameter)]

    # The T is tested with the floor shrunk by the guard band (a sure fit) and grown by it
    # (a sure miss); anything in between is borderline.
    band = ctx.k * sigma
    t_square, t_width = req["t_square"].mm, req["t_width"].mm
    if t_fits(floor.buffer(-band), t_square, t_width) is not None:
        t_verdict = Verdict.PASS
    elif t_fits(floor.buffer(band + CELL_MM), t_square, t_width) is None:
        t_verdict = Verdict.FAIL
    else:
        t_verdict = Verdict.BORDERLINE

    verdict = any_of([circle_verdict, t_verdict])
    shape = (
        "circle"
        if circle_verdict is Verdict.PASS
        else "T-shape"
        if t_verdict is Verdict.PASS
        else None
    )
    parts = [f"largest circle {diameter:.0f} mm", f"T-shape {t_verdict}"]
    if shape:
        parts.append(f"fits as a {shape}")
    parts.append(f"{len(fixtures)} fixture(s) modelled" if fixtures else "no fixtures modelled")
    return CheckOutcome(
        verdict=verdict,
        measured=measured,
        required=(
            f"circle {req['circle_diameter'].as_written()} or "
            f"T in {req['t_square'].as_written()} square"
        ),
        required_mm=req["circle_diameter"].mm,
        reason="; ".join(parts),
        surfaced_exceptions=surfaced,
        evidence=evidence,
    )
