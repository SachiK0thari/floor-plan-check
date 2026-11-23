"""The plan as an SVG drawing, with each finding's evidence drawn on it.

One SVG user unit is one plan millimetre. Plan space has y up and SVG has y down, so every
point goes through ``_Frame.xy``, the only place the flip happens. All drawing text (room
labels, element ids, finding titles) is added through ElementTree, which escapes it.

A finding is drawn from the evidence its check returned. A finding with no drawable
evidence is drawn as the outline of the elements it names, so every finding on an element
can be found on the plan. Verdicts differ by line style as well as colour. A ``fail`` or
``borderline`` finding carries its number from the findings table. An ``unknown`` or
``pass`` that has only an element outline stays hidden until it is selected (the
``pc-active`` class), so a plan is not covered in outlines that report no problem.
"""

from __future__ import annotations

import math
from xml.etree import ElementTree as ET

from shapely.geometry import LineString, Polygon

from plancheck.compliance.engine import Report
from plancheck.compliance.results import Evidence, Finding
from plancheck.model.geometry import (
    door_swing,
    drawing_bounds,
    opening_gap,
    opening_span,
    wall_solids,
)
from plancheck.model.types import BuildingModel, Point

SVG_NS = "http://www.w3.org/2000/svg"
_MIN_POINTS = {"polygon": 3, "line": 2, "point": 1}
_NUMBERED = ("fail", "borderline")
"""Verdicts that report a problem get a numbered badge on the plan."""


def _drawable(evidence: Evidence) -> bool:
    return len(evidence.points) >= _MIN_POINTS[evidence.kind]


def finding_shapes(model: BuildingModel, finding: Finding) -> list[Evidence]:
    """What to draw for a finding: its evidence, or failing that the elements it names."""
    drawn = [e for e in finding.evidence if _drawable(e)]
    if drawn:
        return drawn
    walls = {wall.id: wall for wall in model.walls}
    openings = {opening.id: opening for opening in model.openings}
    rooms = {room.id: room for room in model.rooms}
    shapes: list[Evidence] = []
    for element_id in finding.element_ids:
        if element_id in openings:
            opening = openings[element_id]
            gap = opening_gap(walls[opening.wall_id], opening)
            points = [(float(x), float(y)) for x, y in list(gap.exterior.coords)[:-1]]
            shapes.append(Evidence(kind="polygon", points=points, label=element_id))
        elif element_id in rooms:
            shapes.append(
                Evidence(kind="polygon", points=rooms[element_id].clear_polygon, label=element_id)
            )
    return shapes


class _Frame:
    """Maps plan millimetres to SVG user units and sizes strokes and text for the plan."""

    def __init__(self, bounds: tuple[float, float, float, float]) -> None:
        minx, miny, maxx, maxy = bounds
        self.unit = max(maxx - minx, maxy - miny, 1.0) / 100
        self.margin = 4 * self.unit
        self.minx, self.maxy = minx, maxy
        self.width = maxx - minx + 2 * self.margin
        self.height = maxy - miny + 2 * self.margin

    def xy(self, point: Point) -> tuple[float, float]:
        return (point[0] - self.minx + self.margin, self.maxy + self.margin - point[1])

    def points(self, points: list[Point]) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in map(self.xy, points))


def _bounds(model: BuildingModel, shapes: list[Evidence]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = drawing_bounds(model)
    for shape in shapes:
        for x, y in shape.points:
            minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x), max(maxy, y)
    return (minx, miny, maxx, maxy)


def _style(u: float) -> str:
    """Stroke widths, dashes and text sizes scale with the plan, so the unit is passed in."""
    return (
        f".pc-room{{fill:#f6f3ec;stroke:none}}"
        f".pc-wall{{fill:#2f3a36;stroke:none;fill-rule:evenodd}}"
        f".pc-door{{fill:none;stroke:#2f3a36;stroke-width:{0.18 * u:.1f}}}"
        f".pc-window{{fill:#fff;stroke:#3d6687;stroke-width:{0.18 * u:.1f}}}"
        f".pc-label{{fill:#4a5a52;font:{1.5 * u:.1f}px system-ui,sans-serif;text-anchor:middle}}"
        f".pc-id{{fill:#6b7a72;font:{1.1 * u:.1f}px system-ui,sans-serif;text-anchor:middle}}"
        f".pc-shape{{fill:none;stroke-width:{0.4 * u:.1f};stroke-linejoin:round;"
        f"stroke-linecap:round}}"
        f".pc-area{{fill:currentColor;fill-opacity:.1}}"
        f".pc-finding.v-fail{{color:#b3261e}}"
        f".pc-finding.v-borderline{{color:#8a5a00}}"
        f".pc-finding.v-unknown{{color:#4f5d75;opacity:.5}}"
        f".pc-finding.v-pass{{color:#1a7f37;opacity:.55}}"
        f".pc-finding.v-not_applicable{{display:none}}"
        f".pc-finding.pc-fallback.v-unknown,.pc-finding.pc-fallback.v-pass{{display:none}}"
        f".pc-finding a{{color:inherit;text-decoration:none}}"
        f".pc-finding .pc-shape{{stroke:currentColor}}"
        f".pc-finding.v-borderline .pc-shape{{stroke-dasharray:{1.6 * u:.1f} {0.9 * u:.1f}}}"
        f".pc-finding.v-unknown .pc-shape{{stroke-dasharray:{0.1 * u:.1f} {0.9 * u:.1f}}}"
        f".pc-finding.v-pass .pc-shape{{stroke-width:{0.2 * u:.1f}}}"
        f".pc-badge circle{{fill:#fff;stroke:currentColor;stroke-width:{0.25 * u:.1f}}}"
        f".pc-finding.v-fail .pc-badge circle{{fill:currentColor}}"
        f".pc-badge text{{fill:currentColor;font:bold {1.5 * u:.1f}px system-ui,sans-serif;"
        f"text-anchor:middle}}"
        f".pc-finding.v-fail .pc-badge text{{fill:#fff}}"
        f".pc-finding.pc-active,.pc-finding:target{{display:inline!important;opacity:1}}"
        f".pc-finding.pc-active .pc-shape,.pc-finding:target .pc-shape"
        f"{{stroke-width:{0.8 * u:.1f}}}"
        f".pc-finding.pc-active .pc-area,.pc-finding:target .pc-area{{fill-opacity:.25}}"
        f".pc-finding.v-not_applicable.pc-active{{color:#6b7a72}}"
    )


def _anchor(shape: Evidence) -> Point:
    """A point on or in the shape, for its numbered badge."""
    if shape.kind == "polygon":
        point = Polygon(shape.points).representative_point()
    elif shape.kind == "line":
        point = LineString(shape.points).interpolate(0.5, normalized=True)
    else:
        return shape.points[0]
    return (float(point.x), float(point.y))


def _draw_model(root: ET.Element, model: BuildingModel, frame: _Frame) -> None:
    u = frame.unit
    walls = {wall.id: wall for wall in model.walls}
    rooms = ET.SubElement(root, "g", {"class": "pc-rooms"})
    for room in model.rooms:
        ET.SubElement(
            rooms, "polygon", {"class": "pc-room", "points": frame.points(room.clear_polygon)}
        )
    solids = ET.SubElement(root, "g", {"class": "pc-walls"})
    for solid in wall_solids(model):
        path = " ".join(
            "M"
            + " L".join(f"{x:.1f},{y:.1f}" for x, y in map(frame.xy, list(ring.coords)[:-1]))
            + " Z"
            for ring in (solid.exterior, *solid.interiors)
        )
        ET.SubElement(solids, "path", {"class": "pc-wall", "d": path})
    openings = ET.SubElement(root, "g", {"class": "pc-openings"})
    for opening in model.openings:
        wall = walls[opening.wall_id]
        first, second = opening_span(wall, opening)
        if opening.kind == "window":
            gap = opening_gap(wall, opening)
            outline = [(float(x), float(y)) for x, y in list(gap.exterior.coords)[:-1]]
            ET.SubElement(
                openings, "polygon", {"class": "pc-window", "points": frame.points(outline)}
            )
            ET.SubElement(
                openings,
                "polyline",
                {"class": "pc-window", "points": frame.points([first, second])},
            )
            continue
        swing = door_swing(wall, opening)
        side = wall.left_normal
        if swing is not None:
            hx, hy = frame.xy(swing.hinge)
            lx, ly = frame.xy(swing.latch)
            tx, ty = frame.xy(swing.tip)
            turn = swing.along[0] * swing.outward[1] - swing.along[1] * swing.outward[0]
            # Counter-clockwise on plan is counter-clockwise on screen, which is sweep 0 in SVG.
            sweep = "0" if turn > 0 else "1"
            radius = f"{swing.leaf_mm:.1f}"
            ET.SubElement(
                openings,
                "path",
                {
                    "class": "pc-door",
                    "d": f"M{hx:.1f},{hy:.1f} L{tx:.1f},{ty:.1f} "
                    f"M{lx:.1f},{ly:.1f} A{radius},{radius} 0 0 {sweep} {tx:.1f},{ty:.1f}",
                },
            )
            side = (-swing.outward[0], -swing.outward[1])
        # The id sits beside the opening, on the side the leaf does not swing into.
        offset = wall.thickness.value_mm / 2 + 1.6 * u
        centre = wall.point_at(opening.position_along_wall_mm)
        x, y = frame.xy((centre[0] + side[0] * offset, centre[1] + side[1] * offset))
        label = ET.SubElement(
            openings, "text", {"class": "pc-id", "x": f"{x:.1f}", "y": f"{y + 0.4 * u:.1f}"}
        )
        label.text = opening.id
    labels = ET.SubElement(root, "g", {"class": "pc-labels"})
    for room in model.rooms:
        spot = Polygon(room.clear_polygon).representative_point()
        x, y = frame.xy((float(spot.x), float(spot.y)))
        text = ET.SubElement(
            labels, "text", {"class": "pc-label", "x": f"{x:.1f}", "y": f"{y:.1f}"}
        )
        text.text = room.label or room.id
        if room.label and room.label != room.id:
            sub = ET.SubElement(
                labels, "text", {"class": "pc-id", "x": f"{x:.1f}", "y": f"{y + 1.6 * u:.1f}"}
            )
            sub.text = room.id


def _draw_finding(
    parent: ET.Element,
    number: int,
    finding: Finding,
    shapes: list[Evidence],
    frame: _Frame,
    badges: list[tuple[float, float]],
) -> None:
    u = frame.unit
    verdict = str(finding.verdict)
    # An element outline, drawn because the check returned nothing to draw, is not filled.
    fallback = not any(_drawable(e) for e in finding.evidence)
    area = "pc-shape" if fallback else "pc-shape pc-area"
    group = ET.SubElement(
        parent,
        "g",
        {
            "class": f"pc-finding v-{verdict}" + (" pc-fallback" if fallback else ""),
            "id": f"pc-f{number}",
            "data-finding": str(number),
            "data-verdict": verdict,
            "data-rule": finding.rule_id,
        },
    )
    title = ET.SubElement(group, "title")
    title.text = f"#{number} {verdict}: {finding.title} ({', '.join(finding.element_ids)})"
    for shape in shapes:
        if shape.kind == "polygon":
            ET.SubElement(
                group,
                "polygon",
                {"class": area, "points": frame.points(shape.points)},
            )
        elif shape.kind == "line":
            ET.SubElement(
                group, "polyline", {"class": "pc-shape", "points": frame.points(shape.points)}
            )
        else:
            x, y = frame.xy(shape.points[0])
            ET.SubElement(
                group,
                "circle",
                {"class": area, "cx": f"{x:.1f}", "cy": f"{y:.1f}", "r": f"{u:.1f}"},
            )
    if verdict not in _NUMBERED:
        return
    radius = 1.5 * u
    x, y = frame.xy(_anchor(shapes[0]))
    if fallback:
        y += 3.6 * u  # below the room label, which sits at the same point
    # Several findings on one door share an anchor; step sideways until the badge is clear.
    while any(math.dist((x, y), other) < 2.2 * radius for other in badges):
        x += 2.4 * radius
    badges.append((x, y))
    # The badge links to the finding's row, which the report and the page both name this way.
    link = ET.SubElement(group, "a", {"href": f"#pc-row-{number}"})
    badge = ET.SubElement(link, "g", {"class": "pc-badge"})
    ET.SubElement(badge, "circle", {"cx": f"{x:.1f}", "cy": f"{y:.1f}", "r": f"{radius:.1f}"})
    text = ET.SubElement(badge, "text", {"x": f"{x:.1f}", "y": f"{y + 0.52 * u:.1f}"})
    text.text = str(number)


def plan_svg_element(model: BuildingModel, report: Report | None = None) -> ET.Element:
    """The drawing as an element tree. Findings are numbered from 1 in report order."""
    numbered = list(enumerate(report.findings, start=1)) if report is not None else []
    shapes = {number: finding_shapes(model, finding) for number, finding in numbered}
    frame = _Frame(_bounds(model, [s for group in shapes.values() for s in group]))
    root = ET.Element(
        "svg",
        {
            "xmlns": SVG_NS,
            "viewBox": f"0 0 {frame.width:.1f} {frame.height:.1f}",
            "class": "pc-plan",
            "role": "img",
            "aria-label": "Floor plan with findings" if report is not None else "Floor plan",
        },
    )
    ET.SubElement(root, "style").text = _style(frame.unit)
    _draw_model(root, model, frame)
    findings = ET.SubElement(root, "g", {"class": "pc-findings"})
    badges: list[tuple[float, float]] = []
    # Passes are drawn first so that findings needing attention sit on top of them.
    order = sorted(numbered, key=lambda item: str(item[1].verdict) in _NUMBERED)
    for number, finding in order:
        if shapes[number]:
            _draw_finding(findings, number, finding, shapes[number], frame, badges)
    return root


def plan_svg(model: BuildingModel, report: Report | None = None) -> str:
    """The plan, and each finding's evidence when a report is given, as an SVG document."""
    return ET.tostring(plan_svg_element(model, report), encoding="unicode")
