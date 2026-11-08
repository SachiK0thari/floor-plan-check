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

from plancheck.compliance.checks.opening_clear_width import opening_clear_width
from plancheck.compliance.context import CheckContext
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, all_of
from plancheck.model.types import EXTERIOR, BuildingModel, Room

_LEVELS = (
    (Verdict.PASS,),
    (Verdict.PASS, Verdict.BORDERLINE),
    (Verdict.PASS, Verdict.BORDERLINE, Verdict.UNKNOWN),
)


def _route(model: BuildingModel, target: str, usable: dict[str, Verdict]) -> list[str] | None:
    """Door ids along a route from the exterior to ``target`` using only ``usable`` doors."""
    previous: dict[str, tuple[str, str] | None] = {EXTERIOR: None}
    queue = deque([EXTERIOR])
    while queue:
        node = queue.popleft()
        if node == target:
            doors = []
            while previous[node] is not None:
                node, door = previous[node]  # type: ignore[misc]
                doors.append(door)
            return doors[::-1]
        for edge in model.graph.edges:
            if edge.opening_id not in usable:
                continue
            for here, there in ((edge.a, edge.b), (edge.b, edge.a)):
                if here == node and there not in previous:
                    previous[there] = (node, edge.opening_id)
                    queue.append(there)
    return None


def accessible_route_exists(
    model: BuildingModel, rule: Rule, room: Room, ctx: CheckContext
) -> CheckOutcome:
    width_rule = ctx.door_rule
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]
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
        route = _route(model, room.id, usable)
        if route is not None:
            verdict = all_of(door_verdicts[door] for door in route)
            return CheckOutcome(
                verdict=verdict,
                reason=f"route from the exterior through {', '.join(route)}",
                surfaced_exceptions=surfaced,
                evidence=[Evidence(kind="line", points=[], label=" → ".join(route))],
            )
    return CheckOutcome(
        verdict=Verdict.FAIL,
        reason="no route from the exterior through doors that could comply",
        surfaced_exceptions=surfaced,
    )
