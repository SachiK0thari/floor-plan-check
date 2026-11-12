"""Project applicability shared by amendment layering and check execution."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict
from plancheck.jurisdiction.resolve import AdoptionRecord
from plancheck.model.types import ProjectContext


class Applies(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Verdict  # PASS = applies, NOT_APPLICABLE, or UNKNOWN (input missing)
    reason: str | None = None


def local_applicability(
    jurisdiction: str, project: ProjectContext, records: list[AdoptionRecord]
) -> Applies:
    """Authorize a local layer only against the selected, complete adoption chain."""
    if project.jurisdiction is None:
        return Applies(status=Verdict.UNKNOWN, reason="project input missing: jurisdiction")
    by_slug = {record.slug: record for record in records}
    chain: list[AdoptionRecord] = []
    slug: str | None = project.jurisdiction
    while slug is not None:
        if slug in {record.slug for record in chain}:
            return Applies(status=Verdict.UNKNOWN, reason="adoption chain contains a cycle")
        record = by_slug.get(slug)
        if record is None:
            return Applies(
                status=Verdict.UNKNOWN, reason=f"verified adoption record missing: {slug}"
            )
        chain.append(record)
        slug = record.parent
    if jurisdiction not in {record.slug for record in chain}:
        return Applies(
            status=Verdict.NOT_APPLICABLE,
            reason=f"{jurisdiction} is outside the selected jurisdiction chain",
        )
    for record in chain:
        if record.missing:
            return Applies(
                status=Verdict.UNKNOWN,
                reason=f"adoption record {record.slug} incomplete: {record.missing}",
            )
    if project.permit_date is None:
        return Applies(status=Verdict.UNKNOWN, reason="project input missing: permit_date")
    for record in chain:
        if record.effective_date is not None and project.permit_date < record.effective_date:
            return Applies(
                status=Verdict.NOT_APPLICABLE,
                reason=f"adoption {record.slug} not in force until {record.effective_date}",
            )
    return Applies(status=Verdict.PASS)


def adopted_base_applicability(
    rule: Rule, project: ProjectContext, records: list[AdoptionRecord]
) -> Applies:
    """A loaded model code is not automatically the project's adopted code."""
    if project.jurisdiction is None:
        return Applies(status=Verdict.UNKNOWN, reason="project input missing: jurisdiction")
    local = local_applicability(project.jurisdiction, project, records)
    if local.status is not Verdict.PASS:
        return local
    by_slug = {record.slug: record for record in records}
    slug: str | None = project.jurisdiction
    while slug is not None:
        record = by_slug[slug]
        if (record.base_code, record.base_edition) == (rule.code, rule.edition):
            return Applies(status=Verdict.PASS)
        slug = record.parent
    return Applies(
        status=Verdict.NOT_APPLICABLE,
        reason=f"{rule.code} {rule.edition} is not in the verified adoption chain",
    )


def applicability(rule: Rule, project: ProjectContext, today: date | None = None) -> Applies:
    """Whether the rule is in force. ``today`` is retained for call compatibility only.

    Calendar time cannot substitute for a project's permit application date.
    """
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
    when = project.permit_date
    if when is None and (rule.effective_date or rule.superseded_date):
        missing.append("permit_date")
    if when is not None and rule.effective_date and when < rule.effective_date:
        return Applies(
            status=Verdict.NOT_APPLICABLE,
            reason=f"not in force until {rule.effective_date} (project date {when})",
        )
    if when is not None and rule.superseded_date and when >= rule.superseded_date:
        return Applies(
            status=Verdict.NOT_APPLICABLE,
            reason=f"superseded on {rule.superseded_date} (project date {when})",
        )
    if missing:
        return Applies(status=Verdict.UNKNOWN, reason=f"project input missing: {missing}")
    return Applies(status=Verdict.PASS)
