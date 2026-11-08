"""Running resolved rules against a model, and the report that comes out.

The order of work:

1. Decide, per rule, whether it applies to this project at all (facility type, type of
   work, occupancy, dates). A missing input gives ``unknown``, never a default.
2. Run scoping rules, which produce obligations: groups of elements of which some number
   must comply.
3. Run technical rules on the selected elements, limit each verdict to what the check
   can prove, and roll obligated elements up into group verdicts.
4. Write the coverage statement: what was checked, what was not, and why.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from plancheck.compliance.checks import CHECK_FUNCTIONS
from plancheck.compliance.context import CheckContext
from plancheck.compliance.registry import LoadedRule, ResolvedRules
from plancheck.compliance.results import Finding, Obligation
from plancheck.compliance.rules import Rule
from plancheck.compliance.scoping.doors import SCOPING_FUNCTIONS
from plancheck.compliance.verdict import Verdict, at_least, restrict
from plancheck.model.types import EXTERIOR, BuildingModel, Opening, ProjectContext, Room

NOT_VISIBLE_ON_A_PLAN = [
    "slopes, ramps, and changes in level",
    "thresholds",
    "door hardware, closers, and opening force",
    "mounting heights and reach ranges",
    "signage",
    "protruding objects above the floor",
    "furniture and casework that are not drawn",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Applies(_Base):
    status: Verdict  # PASS = applies, NOT_APPLICABLE, or UNKNOWN (input missing)
    reason: str | None = None


def applicability(rule: Rule, project: ProjectContext, today: date | None = None) -> Applies:
    """Whether the rule is in force for this project."""
    a = rule.applicability
    missing = []
    for field_name, allowed in (
        ("facility_type", a.facility_type),
        ("work_type", a.work_type),
        ("occupancy", a.occupancy),
    ):
        if allowed is None:
            continue
        value = getattr(project, field_name)
        if value is None:
            missing.append(field_name)
        elif value not in allowed:
            return Applies(
                status=Verdict.NOT_APPLICABLE,
                reason=f"{field_name} '{value}' is not one of {allowed}",
            )
    if missing:
        return Applies(status=Verdict.UNKNOWN, reason=f"project input missing: {missing}")
    when = project.permit_date or today or date.today()
    if rule.effective_date and when < rule.effective_date:
        return Applies(
            status=Verdict.NOT_APPLICABLE,
            reason=f"not in force until {rule.effective_date} (project date {when})",
        )
    if rule.superseded_date and when >= rule.superseded_date:
        return Applies(
            status=Verdict.NOT_APPLICABLE,
            reason=f"superseded on {rule.superseded_date} (project date {when})",
        )
    return Applies(status=Verdict.PASS)


def _selected(model: BuildingModel, rule: Rule) -> list[Any]:
    """Elements the rule's selection picks out, before obligations are applied."""
    assert rule.selection is not None
    sel = rule.selection
    exterior_openings = {e.opening_id for e in model.graph.edges if EXTERIOR in (e.a, e.b)}

    def wanted(element: Opening | Room) -> bool:
        for key, allowed in sel.filter.items():
            if key == "exterior":
                if (element.id in exterior_openings) != bool(allowed):
                    return False
                continue
            value = getattr(element, key, None)
            if value not in (allowed if isinstance(allowed, list) else [allowed]):
                return False
        return True

    if sel.element == "opening":
        return [o for o in model.openings if wanted(o)]
    if sel.element == "room":
        return [r for r in model.rooms if wanted(r)]
    return [None]


class Report(_Base):
    rulesets: list[str]
    fingerprint: list[tuple[str, str]]
    findings: list[Finding] = Field(default_factory=list)
    group_findings: list[Finding] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)

    def for_rule(self, rule_id: str) -> list[Finding]:
        return [f for f in self.findings if f.rule_id == rule_id]

    def for_element(self, element_id: str) -> list[Finding]:
        return [f for f in self.findings if element_id in f.element_ids]


def run(
    model: BuildingModel,
    resolved: ResolvedRules,
    ctx: CheckContext | None = None,
    today: date | None = None,
    extra_coverage_notes: list[str] | None = None,
) -> Report:
    ctx = ctx or CheckContext()
    door_rule = next(
        (r.rule for r in resolved.runnable if r.rule.check == "opening_clear_width"), None
    )
    ctx = dataclasses.replace(ctx, door_rule=door_rule)
    project = model.project

    checked: dict[str, Counter[str]] = {}
    not_applicable: list[tuple[str, str]] = []
    unknown_applicability: list[tuple[str, str]] = []
    not_implemented: list[str] = []
    obligations: list[Obligation] = []
    findings: list[Finding] = []
    group_findings: list[Finding] = []

    def gate(loaded: LoadedRule) -> bool:
        applies = applicability(loaded.rule, project, today)
        if applies.status is Verdict.NOT_APPLICABLE:
            not_applicable.append((loaded.rule.id, applies.reason or ""))
            return False
        if applies.status is Verdict.UNKNOWN:
            unknown_applicability.append((loaded.rule.id, applies.reason or ""))
            return False
        return True

    # 1 and 2: scoping rules first, so technical rules can use their obligations.
    scoping = [r for r in resolved.runnable if r.rule.kind == "scoping"]
    technical = [r for r in resolved.runnable if r.rule.kind == "technical"]
    for loaded in scoping:
        function = SCOPING_FUNCTIONS.get(loaded.rule.check or "")
        if function is None:
            not_implemented.append(loaded.rule.id)
            continue
        if gate(loaded):
            obligations.extend(function(model, loaded.rule))
            checked[loaded.rule.id] = Counter()

    # 3: technical rules.
    for loaded in technical:
        rule = loaded.rule
        function = CHECK_FUNCTIONS.get(rule.check or "")
        if function is None:
            not_implemented.append(rule.id)
            continue
        if not gate(loaded):
            continue
        counts: Counter[str] = Counter()
        checked[rule.id] = counts
        elements = _selected(model, rule)
        assert rule.selection is not None
        obligated_by = rule.selection.obligated_by
        relevant = [o for o in obligations if o.scoping_rule_id in obligated_by]
        if obligated_by:
            obligated_ids = {eid for o in relevant for eid in o.element_ids}
            elements = [e for e in elements if e is not None and e.id in obligated_ids]
        by_element: dict[str, Verdict] = {}
        for element in elements:
            outcome = function(model, rule, element, ctx)
            verdict = restrict(outcome.verdict, rule.proves or "both")
            reason = outcome.reason
            if verdict is Verdict.UNKNOWN and outcome.verdict is not Verdict.UNKNOWN:
                reason = (
                    f"check can only prove {rule.proves.replace('_', ' ') if rule.proves else ''}; "
                    + (reason or "")
                )
            element_ids = [element.id] if element is not None else []
            finding = Finding(
                rule_id=rule.id,
                code=rule.code,
                section=rule.section,
                title=rule.title,
                verdict=verdict,
                element_ids=element_ids,
                measured=outcome.measured,
                required=outcome.required,
                required_mm=outcome.required_mm,
                reason=reason,
                obligations=[
                    o.reason
                    for o in relevant
                    if element is not None and element.id in o.element_ids
                ],
                surfaced_exceptions=outcome.surfaced_exceptions,
                evidence=outcome.evidence,
            )
            findings.append(finding)
            counts[str(verdict)] += 1
            if element is not None:
                by_element[element.id] = verdict
        # Roll obligated elements up: "at least N of these must comply".
        for obligation in relevant:
            members = [by_element.get(eid, Verdict.UNKNOWN) for eid in obligation.element_ids]
            group_verdict = at_least(obligation.min_count, members)
            group_findings.append(
                Finding(
                    rule_id=rule.id,
                    code=rule.code,
                    section=rule.section,
                    title=rule.title,
                    verdict=group_verdict,
                    element_ids=list(obligation.element_ids),
                    reason=obligation.reason,
                    group=obligation.group_id,
                )
            )

    # 4: coverage.
    coverage: dict[str, Any] = {
        "checked": {rule_id: dict(counts) for rule_id, counts in checked.items()},
        "not_applicable": not_applicable,
        "unknown_applicability": unknown_applicability,
        "not_runnable": list(resolved.not_runnable),
        "not_implemented": not_implemented,
        "amendments": list(resolved.notes),
        "not_visible_on_a_plan": list(NOT_VISIBLE_ON_A_PLAN),
        "notes": list(extra_coverage_notes or []),
    }
    if not unknown_applicability and not not_applicable and model.project.permit_date is None:
        coverage["notes"].append("no permit date given; rules in force today were applied")
    return Report(
        rulesets=resolved.rulesets,
        fingerprint=resolved.fingerprint(),
        findings=findings,
        group_findings=group_findings,
        obligations=obligations,
        coverage=coverage,
    )
