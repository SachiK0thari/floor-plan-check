"""Door clear width (serves 2010 ADA 404.2.3)."""

from __future__ import annotations

from plancheck.compliance.context import CheckContext
from plancheck.compliance.results import CheckOutcome, Evidence
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, decide_min
from plancheck.model.geometry import opening_span
from plancheck.model.types import BuildingModel, Opening


def opening_clear_width(
    model: BuildingModel, rule: Rule, opening: Opening, ctx: CheckContext
) -> CheckOutcome:
    """Compare the opening's clear width with the rule's minimum.

    Checked exceptions: an opening deeper than the stated depth (here, the wall
    thickness) needs the larger minimum; a double-leaf door is judged on one active
    leaf, which is what ``leaf_width`` holds.
    """
    wall = model.wall(opening.wall_id)
    evidence = [Evidence(kind="line", points=list(opening_span(wall, opening)), label=opening.id)]
    surfaced = [e.id for e in rule.exceptions if e.handling == "surfaced"]

    measured, how = ctx.clear_width(opening)
    if measured is None:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason=how,
            surfaced_exceptions=surfaced,
            evidence=evidence,
        )

    required = rule.requirement["min_clear_width"]
    notes = [how or ""]
    deep = next((e for e in rule.exceptions if e.id == "deep-opening"), None)
    if deep is not None and wall.thickness.value_mm > deep.params["depth"].mm:
        required = deep.params["min_clear_width"]
        notes.append(
            f"opening deeper than {deep.params['depth'].as_written()}: larger minimum applies"
        )
    if opening.operation == "double_swing":
        notes.append("double-leaf door: one active leaf is judged")

    return CheckOutcome(
        verdict=decide_min(measured, required.mm, ctx.k),
        measured=measured,
        required=required.as_written(),
        required_mm=required.mm,
        reason="; ".join(notes),
        surfaced_exceptions=surfaced,
        evidence=evidence,
    )
