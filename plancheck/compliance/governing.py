"""Derive scalar requirements without merging or changing source verdicts."""

from __future__ import annotations

import math
from collections import defaultdict

from plancheck.compliance.registry import LoadedRule
from plancheck.compliance.results import (
    ComparisonOmission,
    Finding,
    GoverningRequirement,
    RuleCitation,
)
from plancheck.compliance.verdict import Verdict

# Used only to keep unresolved findings in the right candidate group. A match here
# does not authorize comparison: every source must also supply measurement semantics.
_CHECK_QUANTITIES = {"opening_clear_width": "opening.clear_width"}


def cite(finding: Finding, loaded: LoadedRule) -> Finding:
    rule = loaded.rule
    return finding.model_copy(
        update={
            "regime": "ada" if loaded.ruleset == "ada_2010" else "building_code",
            "citation": RuleCitation(
                code=rule.code,
                edition=rule.edition,
                section=rule.section,
                source_url=rule.source_url,
                jurisdiction=rule.jurisdiction,
                ruleset=loaded.ruleset,
                effective_date=rule.effective_date,
                superseded_date=rule.superseded_date,
            ),
        }
    )


def derive_governing(
    findings: list[Finding], rules: dict[str, LoadedRule]
) -> tuple[list[GoverningRequirement], list[ComparisonOmission]]:
    buckets: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    unresolved_rules: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        if finding.group is not None or finding.verdict is Verdict.NOT_APPLICABLE:
            continue
        rule = rules[finding.rule_id].rule
        check = rule.check
        if check is None and rule.amends is not None:
            check = rules[rule.amends.rule].rule.check
        quantity = (
            finding.semantics.quantity
            if finding.semantics is not None
            else _CHECK_QUANTITIES.get(check or "", check or rule.id)
        )
        if not finding.element_ids:
            if finding.verdict is Verdict.UNKNOWN:
                unresolved_rules[quantity].append(finding)
            continue
        if len(finding.element_ids) == 1:
            buckets[(finding.element_ids[0], quantity)].append(finding)
    governing = []
    omitted = []
    for (element_id, quantity), members in sorted(buckets.items()):
        sources = sorted([*members, *unresolved_rules[quantity]], key=lambda f: f.rule_id)
        if {f.regime for f in sources} != {"ada", "building_code"}:
            continue
        reason = None
        if any(f.provisional for f in sources):
            reason = "proposed jurisdiction needs confirmation"
        elif any(rules[f.rule_id].rule.status != "verified" for f in sources):
            reason = "one or more source rules are unverified"
        elif any(f.semantics is None for f in sources):
            reason = "measurement semantics unavailable or applicability unresolved"
        elif any(f.semantics is not None and f.semantics.unresolved_conditions for f in sources):
            reason = "unresolved exceptions or measurement conditions: " + "; ".join(
                f"{f.rule_id}: {', '.join(f.semantics.unresolved_conditions)}"
                for f in sources
                if f.semantics is not None and f.semantics.unresolved_conditions
            )
        elif any(
            f.verdict not in (Verdict.PASS, Verdict.FAIL, Verdict.BORDERLINE)
            or f.required_mm is None
            or f.required is None
            or f.measured is None
            for f in sources
        ):
            reason = "applicability or scalar measurement is unresolved"
        else:
            first = sources[0]
            assert first.semantics is not None
            if any(
                f.semantics is None
                or (f.semantics.basis, f.semantics.relation)
                != (first.semantics.basis, first.semantics.relation)
                for f in sources
            ):
                reason = "measurement basis or bound direction differs"
            elif any(f.measured != first.measured for f in sources):
                reason = "measurements or their uncertainty/provenance differ"
        if reason is not None:
            omitted.append(
                ComparisonOmission(
                    element_id=element_id,
                    quantity=quantity,
                    rule_ids=[f.rule_id for f in sources],
                    reason=reason,
                )
            )
            continue
        first = sources[0]
        assert first.semantics is not None
        limits = [f.required_mm for f in sources if f.required_mm is not None]
        limit = max(limits) if first.semantics.relation == "min" else min(limits)
        winners = [
            f
            for f in sources
            if f.required_mm is not None
            and math.isclose(f.required_mm, limit, rel_tol=0, abs_tol=1e-6)
        ]
        governing.append(
            GoverningRequirement(
                element_id=element_id,
                quantity=quantity,
                basis=first.semantics.basis,
                relation=first.semantics.relation,
                required_mm=limit,
                required=winners[0].required or "",
                governing_rule_ids=[f.rule_id for f in winners],
                source_findings=sources,
                reason="most restrictive applicable "
                + first.semantics.relation
                + " bound on the same measured quantity; source verdicts remain separate",
            )
        )
    return governing, omitted
