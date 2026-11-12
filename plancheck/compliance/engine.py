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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from plancheck.compliance.applicability import (
    Applies,
    adopted_base_applicability,
    applicability,
    local_applicability,
)
from plancheck.compliance.checks import CHECK_FUNCTIONS
from plancheck.compliance.context import CheckContext, connectivity_gaps
from plancheck.compliance.governing import cite, derive_governing
from plancheck.compliance.registry import AmendmentRecord, LoadedRule, ResolvedRules
from plancheck.compliance.results import (
    ComparisonOmission,
    Finding,
    GoverningRequirement,
    Obligation,
)
from plancheck.compliance.rules import Rule
from plancheck.compliance.scoping.doors import SCOPING_FUNCTIONS
from plancheck.compliance.verdict import Verdict, restrict, scoped_at_least
from plancheck.jurisdiction.resolve import AdoptionRecord, load_adoption_records
from plancheck.model.types import EXTERIOR, BuildingModel, Opening, Room

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


def _selection(model: BuildingModel, rule: Rule) -> list[tuple[Opening | Room | None, Applies]]:
    """Resolve selection without mistaking a missing attribute for an exclusion."""
    assert rule.selection is not None
    sel = rule.selection
    exterior_openings = {e.opening_id for e in model.graph.edges if EXTERIOR in (e.a, e.b)}

    connected = {e.opening_id for e in model.graph.edges}

    def wanted(element: Opening | Room) -> Applies:
        missing = []
        for key, allowed in sel.filter.items():
            if key == "exterior":
                if element.id not in connected:
                    missing.append("room-graph connection (exterior status)")
                    continue
                if (element.id in exterior_openings) != bool(allowed):
                    return Applies(
                        status=Verdict.NOT_APPLICABLE,
                        reason=f"selection excludes {element.id}: exterior != {allowed}",
                    )
                continue
            value = getattr(element, key, None)
            if value is None:
                missing.append(key)
                continue
            if value not in (allowed if isinstance(allowed, list) else [allowed]):
                return Applies(
                    status=Verdict.NOT_APPLICABLE,
                    reason=f"selection excludes {element.id}: {key} '{value}' "
                    f"is not one of {allowed}",
                )
        if missing:
            return Applies(
                status=Verdict.UNKNOWN, reason=f"element input missing for {element.id}: {missing}"
            )
        return Applies(status=Verdict.PASS)

    if sel.element == "opening":
        return [(o, wanted(o)) for o in model.openings]
    if sel.element == "room":
        return [(r, wanted(r)) for r in model.rooms]
    return [(None, Applies(status=Verdict.PASS))]


class Report(_Base):
    rulesets: list[str]
    fingerprint: list[tuple[str, str]]
    findings: list[Finding] = Field(default_factory=list)
    group_findings: list[Finding] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    governing_requirements: list[GoverningRequirement] = Field(default_factory=list)
    governing_not_derived: list[ComparisonOmission] = Field(default_factory=list)
    amendments: list[AmendmentRecord] = Field(default_factory=list)

    def for_rule(self, rule_id: str) -> list[Finding]:
        return [f for f in self.findings if f.rule_id == rule_id]

    def for_element(self, element_id: str) -> list[Finding]:
        return [f for f in self.findings if element_id in f.element_ids]

    def for_regime(self, regime: Literal["ada", "building_code"]) -> list[Finding]:
        return [f for f in self.findings if f.regime == regime]


def run(
    model: BuildingModel,
    resolved: ResolvedRules,
    ctx: CheckContext | None = None,
    today: date | None = None,
    extra_coverage_notes: list[str] | None = None,
    adoption_records: list[AdoptionRecord] | None = None,
) -> Report:
    records = load_adoption_records() if adoption_records is None else adoption_records
    local_status = {
        r.rule.jurisdiction: local_applicability(r.rule.jurisdiction, model.project, records)
        for r in resolved.source_rules + resolved.rules
        if r.rule.jurisdiction is not None
    }
    resolved = resolved.for_project(model.project, local_status)
    ctx = ctx or CheckContext()
    project = model.project

    def applies_to_project(loaded: LoadedRule) -> Applies:
        applies = applicability(loaded.rule, project, today)
        if loaded.rule.jurisdiction is not None:
            local = local_status[loaded.rule.jurisdiction]
            if applies.status is not Verdict.NOT_APPLICABLE and local.status is not Verdict.PASS:
                applies = local
        elif loaded.ruleset != "ada_2010" and applies.status is not Verdict.NOT_APPLICABLE:
            adopted = adopted_base_applicability(loaded.rule, project, records)
            if adopted.status is not Verdict.PASS:
                applies = adopted
        return applies

    checked: dict[str, Counter[str]] = {}
    not_applicable: list[tuple[str, str]] = []
    unknown_applicability: list[tuple[str, str]] = []
    not_implemented: list[str] = []
    obligations: list[Obligation] = []
    findings: list[Finding] = []
    group_findings: list[Finding] = []
    scope_status: dict[str, Applies] = {}
    rules_by_id = {loaded.rule.id: loaded.rule for loaded in resolved.rules}
    loaded_by_id = {loaded.rule.id: loaded for loaded in resolved.source_rules + resolved.rules}
    scoping_exceptions: list[dict[str, Any]] = []

    def surfaced(rule: Rule, relevant: list[Obligation] | None = None) -> list[str]:
        sources = [rule, *(rules_by_id[o.scoping_rule_id] for o in relevant or [])]
        return sorted(
            {e.id for source in sources for e in source.exceptions if e.handling == "surfaced"}
        )

    def skipped(rule: Rule, result: Applies, element: Opening | Room | None = None) -> None:
        findings.append(
            Finding(
                rule_id=rule.id,
                code=rule.code,
                section=rule.section,
                title=rule.title,
                verdict=result.status,
                element_ids=[element.id] if element is not None else [],
                reason=result.reason,
                surfaced_exceptions=surfaced(rule),
            )
        )

    def gate(loaded: LoadedRule) -> bool:
        applies = applies_to_project(loaded)
        if loaded.rule.kind == "scoping":
            scope_status[loaded.rule.id] = applies
        if applies.status is Verdict.NOT_APPLICABLE:
            not_applicable.append((loaded.rule.id, applies.reason or ""))
            skipped(loaded.rule, applies)
            return False
        if applies.status is Verdict.UNKNOWN:
            unknown_applicability.append((loaded.rule.id, applies.reason or ""))
            skipped(loaded.rule, applies)
            return False
        return True

    for rule_id, reason in resolved.not_runnable:
        rule = rules_by_id.get(rule_id)
        if rule is not None:
            result = Applies(status=Verdict.UNKNOWN, reason=f"rule not runnable: {reason}")
            skipped(rule, result)
            if rule.kind == "scoping":
                scope_status[rule.id] = result

    # Inactive/pending amendments are visible even when they have no executable check
    # (notably deletions). Their original rules and citations remain in the audit list.
    active_ids = set(rules_by_id)
    for amendment in resolved.amendments:
        if amendment.status != "applied" and amendment.amending_rule.id not in active_ids:
            skipped(
                amendment.amending_rule,
                Applies(
                    status=Verdict.NOT_APPLICABLE
                    if amendment.status == "not_applicable"
                    else Verdict.UNKNOWN,
                    reason=amendment.reason,
                ),
            )

    # 1 and 2: scoping rules first, so technical rules can use their obligations.
    scoping = [r for r in resolved.runnable if r.rule.kind == "scoping"]
    technical = [r for r in resolved.runnable if r.rule.kind == "technical"]
    for loaded in scoping:
        function = SCOPING_FUNCTIONS.get(loaded.rule.check or "")
        if function is None:
            not_implemented.append(loaded.rule.id)
            scope_status[loaded.rule.id] = Applies(
                status=Verdict.UNKNOWN, reason="scoping check is not implemented"
            )
            skipped(loaded.rule, scope_status[loaded.rule.id])
            continue
        if gate(loaded):
            # An omitted connectivity record cannot establish that a door is exempt.
            if loaded.rule.check in ("doors_serving_rooms", "entrance_doors"):
                missing = connectivity_gaps(
                    model, include_rooms=loaded.rule.check == "doors_serving_rooms"
                )
                if missing:
                    status = Applies(
                        status=Verdict.UNKNOWN,
                        reason=f"room-graph connectivity missing for {sorted(missing)}",
                    )
                    scope_status[loaded.rule.id] = status
                    skipped(loaded.rule, status)
                    continue
            obligations.extend(function(model, loaded.rule))
            checked[loaded.rule.id] = Counter()
            if surfaced(loaded.rule):
                scoping_exceptions.append(
                    {
                        "rule_id": loaded.rule.id,
                        "element_ids": sorted(
                            {
                                eid
                                for o in obligations
                                if o.scoping_rule_id == loaded.rule.id
                                for eid in o.element_ids
                            }
                        ),
                        "exceptions": surfaced(loaded.rule),
                    }
                )

    # 3: technical rules.
    for loaded in technical:
        rule = loaded.rule
        function = CHECK_FUNCTIONS.get(rule.check or "")
        if function is None:
            not_implemented.append(rule.id)
            skipped(rule, Applies(status=Verdict.UNKNOWN, reason="check is not implemented"))
            continue
        if not gate(loaded):
            continue
        # A route must use its own regime's width requirement, regardless of load order.
        candidates = [
            r
            for r in resolved.runnable
            if r.rule.check == "opening_clear_width"
            and (r.ruleset == "ada_2010") == (loaded.ruleset == "ada_2010")
            and applies_to_project(r).status is Verdict.PASS
        ]
        matching = [
            r for r in candidates if (r.rule.code, r.rule.edition) == (rule.code, rule.edition)
        ]
        candidates = matching or candidates
        check_ctx = dataclasses.replace(
            ctx, door_rule=candidates[0].rule if len(candidates) == 1 else None
        )
        counts: Counter[str] = Counter()
        checked[rule.id] = counts
        elements = _selection(model, rule)
        assert rule.selection is not None
        obligated_by = rule.selection.obligated_by
        relevant = [o for o in obligations if o.scoping_rule_id in obligated_by]
        obligated_ids = {eid for o in relevant for eid in o.element_ids}
        unresolved_scope = [
            scope_id
            for scope_id in obligated_by
            if scope_id not in scope_status or scope_status[scope_id].status is Verdict.UNKNOWN
        ]
        by_element: dict[str, Verdict] = {}
        for element, selection in elements:
            if selection.status is not Verdict.PASS:
                skipped(rule, selection, element)
                if element is not None:
                    by_element[element.id] = selection.status
                continue
            if unresolved_scope:
                reasons = [
                    f"{sid}: {scope_status[sid].reason}"
                    if sid in scope_status
                    else f"{sid}: scoping rule unavailable or not runnable"
                    for sid in unresolved_scope
                ]
                skipped(
                    rule,
                    Applies(
                        status=Verdict.UNKNOWN, reason="scoping unresolved: " + "; ".join(reasons)
                    ),
                    element,
                )
                continue
            if obligated_by and (element is None or element.id not in obligated_ids):
                skipped(
                    rule,
                    Applies(
                        status=Verdict.NOT_APPLICABLE,
                        reason="excluded by resolved scoping: no obligation from "
                        + "; ".join(
                            sid
                            + (f" ({scope_status[sid].reason})" if scope_status[sid].reason else "")
                            for sid in obligated_by
                        ),
                    ),
                    element,
                )
                continue
            outcome = function(model, rule, element, check_ctx)
            element_obligations = [
                o for o in relevant if element is not None and element.id in o.element_ids
            ]
            semantics = outcome.semantics
            if (
                semantics is not None
                and element_obligations
                and all(surfaced(rules_by_id[o.scoping_rule_id]) for o in element_obligations)
            ):
                conditions = semantics.unresolved_conditions + [
                    f"scoping {o.scoping_rule_id}: {exception}"
                    for o in element_obligations
                    for exception in surfaced(rules_by_id[o.scoping_rule_id])
                ]
                semantics = semantics.model_copy(update={"unresolved_conditions": conditions})
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
                surfaced_exceptions=sorted(
                    set(outcome.surfaced_exceptions)
                    | set(
                        surfaced(
                            rule,
                            [
                                o
                                for o in relevant
                                if element is not None and element.id in o.element_ids
                            ],
                        )
                    )
                ),
                evidence=outcome.evidence,
                semantics=semantics,
            )
            findings.append(finding)
            counts[str(verdict)] += 1
            if element is not None:
                by_element[element.id] = verdict
        # Roll obligated elements up: "at least N of these must comply".
        for obligation in relevant:
            members = [by_element.get(eid, Verdict.UNKNOWN) for eid in obligation.element_ids]
            group_verdict = scoped_at_least(obligation.min_count, members)
            group_findings.append(
                Finding(
                    rule_id=rule.id,
                    code=rule.code,
                    section=rule.section,
                    title=rule.title,
                    verdict=group_verdict,
                    element_ids=list(obligation.element_ids),
                    reason=obligation.reason,
                    surfaced_exceptions=sorted(
                        {
                            exception
                            for f in findings
                            if f.rule_id == rule.id
                            and set(f.element_ids) & set(obligation.element_ids)
                            for exception in f.surfaced_exceptions
                        }
                        | set(surfaced(rule, [obligation]))
                    ),
                    group=obligation.group_id,
                )
            )

    findings = [cite(finding, loaded_by_id[finding.rule_id]) for finding in findings]
    group_findings = [cite(finding, loaded_by_id[finding.rule_id]) for finding in group_findings]
    if project.jurisdiction_source == "address_proposed":
        findings = [
            f.model_copy(update={"provisional": f.regime == "building_code"}) for f in findings
        ]
        group_findings = [
            f.model_copy(update={"provisional": f.regime == "building_code"})
            for f in group_findings
        ]
    governing, governing_not_derived = derive_governing(findings, loaded_by_id)

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
        "excluded": [
            f.model_dump(mode="json") for f in findings if f.verdict is Verdict.NOT_APPLICABLE
        ],
        "unresolved": [
            f.model_dump(mode="json")
            for f in findings
            if f.verdict in (Verdict.UNKNOWN, Verdict.BORDERLINE) or f.provisional
        ],
        "surfaced_exceptions": scoping_exceptions
        + [
            {
                "rule_id": f.rule_id,
                "element_ids": f.element_ids,
                "exceptions": f.surfaced_exceptions,
            }
            for f in findings
            if f.surfaced_exceptions
        ],
        "governing_not_derived": [item.model_dump(mode="json") for item in governing_not_derived],
        "amendment_details": [item.model_dump(mode="json") for item in resolved.amendments],
    }
    return Report(
        rulesets=resolved.rulesets,
        fingerprint=resolved.fingerprint(),
        findings=findings,
        group_findings=group_findings,
        obligations=obligations,
        coverage=coverage,
        governing_requirements=governing,
        governing_not_derived=governing_not_derived,
        amendments=resolved.amendments,
    )
