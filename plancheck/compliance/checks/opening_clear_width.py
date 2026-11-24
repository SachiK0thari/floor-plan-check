"""Door clear width (serves 2010 ADA 404.2.3)."""

from __future__ import annotations

from plancheck.compliance.context import CheckContext
from plancheck.compliance.results import CheckOutcome, Evidence, MeasurementSemantics
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, decide_max, decide_min, same_or_borderline
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
    conditions = [
        e
        for e in surfaced
        if not (e == "alteration-latch-stop" and model.project.work_type == "new")
    ]
    conditions.extend(
        e.id
        for e in rule.exceptions
        if e.handling == "checked" and e.id not in {"deep-opening", "double-leaf"}
    )
    deep = next((e for e in rule.exceptions if e.id == "deep-opening"), None)
    if deep is not None and wall.thickness.sigma_mm > 0:
        band = ctx.k * wall.thickness.sigma_mm
        if (
            wall.thickness.value_mm - band
            <= deep.params["depth"].mm
            < wall.thickness.value_mm + band
        ):
            conditions.append("uncertain deep-opening threshold")
    semantics = MeasurementSemantics(
        quantity="opening.clear_width",
        relation="min",
        basis="one_active_leaf" if opening.operation == "double_swing" else "clear_opening",
        unresolved_conditions=conditions,
    )

    measured, how = ctx.clear_width(opening)
    if measured is None:
        return CheckOutcome(
            verdict=Verdict.UNKNOWN,
            reason=how,
            surfaced_exceptions=surfaced,
            evidence=evidence,
            semantics=semantics,
        )

    required = rule.requirement["min_clear_width"]
    notes = [how or ""]
    verdict = decide_min(measured, required.mm, ctx.k)
    if deep is not None:
        # Whether the opening is "deep" is itself a measurement, so it goes through the
        # verdict rule too: PASS means surely not deeper than the stated depth.
        depth = deep.params["depth"]
        larger = deep.params["min_clear_width"]
        membership = decide_max(wall.thickness, depth.mm, ctx.k)
        if membership is Verdict.FAIL:
            verdict, required = decide_min(measured, larger.mm, ctx.k), larger
            notes.append(f"opening deeper than {depth.as_written()}: larger minimum applies")
        elif membership is not Verdict.PASS:
            verdict = same_or_borderline(verdict, decide_min(measured, larger.mm, ctx.k))
            notes.append(
                f"wall thickness is within its uncertainty of {depth.as_written()}, so either "
                f"{required.as_written()} or {larger.as_written()} applies"
            )
            required = larger
    if opening.operation == "double_swing":
        notes.append("double-leaf door: one active leaf is judged")

    return CheckOutcome(
        verdict=verdict,
        measured=measured,
        required=required.as_written(),
        required_mm=required.mm,
        reason="; ".join(notes),
        surfaced_exceptions=surfaced,
        evidence=evidence,
        semantics=semantics,
    )
