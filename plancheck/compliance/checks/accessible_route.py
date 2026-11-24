"""Accessible route from an entrance to a room (serves 2010 ADA 206.2.4).

The room graph is searched from the exterior to the room, using doors in order of how
sure their clear-width verdicts are: first through doors that pass, then also through
borderline ones, then also through unknown ones. The route's verdict is the weakest
door on the best route found. No route at all is a fail.

A route on plan is not proof of an accessible route (steps and slopes are not drawn), so
the rule that uses this check declares ``proves: fail_only``.
"""

from __future__ import annotations

from collections import deque

from shapely.geometry import Polygon

from plancheck.compliance.checks.opening_clear_width import opening_clear_width
from plancheck.compliance.context import CheckContext, connectivity_gaps
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, all_of
from plancheck.model.geometry import opening_span
from plancheck.model.types import EXTERIOR, BuildingModel, Point, Room

_LEVELS = (
    (Verdict.PASS,),
    (Verdict.PASS, Verdict.BORDERLINE),
    (Verdict.PASS, Verdict.BORDERLINE, Verdict.UNKNOWN),
)


def _route(
    model: BuildingModel, target: str, usable: dict[str, Verdict]
) -> list[tuple[str, str]] | None:
    """(door id, room entered) along a route from the exterior to ``target``.

    Only ``usable`` doors are used.
    """
    previous: dict[str, tuple[str, str] | None] = {EXTERIOR: None}
    queue = deque([EXTERIOR])
    while queue:
        node = queue.popleft()
        if node == target:
            steps = []
            while (step := previous[node]) is not None:
                steps.append((step[1], node))
                node = step[0]
            return steps[::-1]
        for edge in model.graph.edges:
            if edge.opening_id not in usable:
                continue
            for here, there in ((edge.a, edge.b), (edge.b, edge.a)):
                if here == node and there not in previous:
                    previous[there] = (node, edge.opening_id)
                    queue.append(there)
    return None


def route_line(model: BuildingModel, steps: list[tuple[str, str]]) -> list[Point]:
    """A polyline for drawing: each door's midpoint, then a point inside the room it opens into.

    The room point is a representative point of the room's clear polygon, so it is always
    inside the room. The line shows which doors the route uses, not a walking path.
    """
    points: list[Point] = []
    for door_id, room_id in steps:
        opening = model.opening(door_id)
        (x0, y0), (x1, y1) = opening_span(model.wall(opening.wall_id), opening)
        points.append(((x0 + x1) / 2, (y0 + y1) / 2))
        inside = Polygon(model.room(room_id).clear_polygon).representative_point()
        points.append((inside.x, inside.y))
    return points


def accessible_route_exists(
    model: BuildingModel, rule: Rule, room: Room, ctx: CheckContext
) -> CheckOutcome:
    width_rule = ctx.door_rule
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]
    missing = connectivity_gaps(model)
    if missing:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason=f"room-graph connectivity missing for {missing}",
            surfaced_exceptions=surfaced,
        )
    if width_rule is None:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason="no door clear width rule in the run, so doors cannot be judged",
            surfaced_exceptions=surfaced,
        )
    door_verdicts = {
        o.id: opening_clear_width(model, width_rule, o, ctx).verdict
        for o in model.openings
        if o.kind in ("door", "opening")
    }
    for allowed in _LEVELS:
        usable = {door: v for door, v in door_verdicts.items() if v in allowed}
        steps = _route(model, room.id, usable)
        if steps is not None:
            route = [door for door, _ in steps]
            verdict = all_of(door_verdicts[door] for door in route)
            return CheckOutcome(
                verdict=verdict,
                reason=f"route from the exterior through {', '.join(route)}",
                surfaced_exceptions=surfaced,
                evidence=[
                    Evidence(kind="line", points=route_line(model, steps), label=" → ".join(route))
                ],
            )
    return CheckOutcome(
        verdict=Verdict.FAIL,
        reason="no route from the exterior through doors that could comply",
        surfaced_exceptions=surfaced,
    )
