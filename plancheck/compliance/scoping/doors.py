"""Scoping rules for doors: which doors must comply, and how many of each group."""

from __future__ import annotations

import math

from plancheck.compliance.contracts import CheckSpec
from plancheck.compliance.results import Obligation
from plancheck.compliance.rules import Rule
from plancheck.model.types import EXTERIOR, BuildingModel

PASSAGE_KINDS = ("door", "opening")


def doors_serving_rooms(model: BuildingModel, rule: Rule) -> list[Obligation]:
    """At least one door or doorway serving each room must comply (2010 ADA 206.5.2)."""
    serving: dict[str, list[str]] = {room.id: [] for room in model.rooms}
    for edge in model.graph.edges:
        if model.opening(edge.opening_id).kind not in PASSAGE_KINDS:
            continue
        for node in (edge.a, edge.b):
            if node in serving and edge.opening_id not in serving[node]:
                serving[node].append(edge.opening_id)
    return [
        Obligation(
            scoping_rule_id=rule.id,
            group_id=f"room:{room_id}",
            element_ids=sorted(openings),
            min_count=1,
            reason=f"at least one door serving {room_id} must comply ({rule.section})",
        )
        for room_id, openings in serving.items()
    ]


def entrance_doors(model: BuildingModel, rule: Rule) -> list[Obligation]:
    """A minimum share of public entrances must comply (2010 ADA 206.4.1).

    The plan does not say which exterior doors are public entrances, so every exterior
    door counts; the rule's surfaced exception says so on each result.
    """
    exterior = sorted(
        {
            edge.opening_id
            for edge in model.graph.edges
            if EXTERIOR in (edge.a, edge.b) and model.opening(edge.opening_id).kind in PASSAGE_KINDS
        }
    )
    share = rule.requirement["min_share"].fraction
    needed = math.ceil(len(exterior) * share - 1e-9) if exterior else 0
    return [
        Obligation(
            scoping_rule_id=rule.id,
            group_id="entrances",
            element_ids=exterior,
            min_count=max(needed, 1 if exterior else 0),
            reason=(
                f"at least {share:.0%} of entrances ({needed} of {len(exterior)}) must comply "
                f"({rule.section}); every exterior door is counted as a public entrance"
            ),
            # No exterior door is far more likely an incomplete model than a building
            # without an entrance, so "0 of 0" must not pass.
            unresolved_reason=None
            if exterior
            else (
                "no exterior door or doorway is modelled; public entrances cannot be "
                f"identified ({rule.section})"
            ),
        )
    ]


SCOPING: dict[str, CheckSpec] = {
    "doors_serving_rooms": CheckSpec(
        function=doors_serving_rooms,
        element="opening",
        proves=None,
        connectivity="openings_and_rooms",
    ),
    "entrance_doors": CheckSpec(
        function=entrance_doors,
        element="opening",
        proves=None,
        requirement={"min_share": "percent"},
        connectivity="openings",
    ),
}

SCOPING_FUNCTIONS = {name: spec.function for name, spec in SCOPING.items()}
