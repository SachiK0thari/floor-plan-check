"""Conservative, offline authority proposals; drawing text never confirms a project."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from plancheck.jurisdiction.location_evidence import LocationExtraction
from plancheck.jurisdiction.resolve import AdoptionRecord


def normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    site_address: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    authority: str = ""
    permit_date: date | None = None
    confirmed: bool = False
    ada_reference: bool = False
    facility_type: str = ""
    occupancy: str = ""
    work_type: Literal["new", "alteration", "existing"] | None = None
    sprinklered: bool | None = None
    scale_mm_per_point: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @property
    def complete(self) -> bool:
        return bool(self.country and self.region and self.authority and self.permit_date)


class Proposal(BaseModel):
    settings: ProjectSettings
    matched_slugs: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def propose(extraction: LocationExtraction, records: list[AdoptionRecord]) -> Proposal:
    values: dict[str, str] = {}
    for candidate in extraction.candidates:
        if candidate.field not in extraction.conflicting_fields:
            values[candidate.field] = candidate.value
    country = values.get("country", "")
    country = {"india": "IN", "united states": "US", "usa": "US"}.get(
        normalized(country), country.upper()
    )
    settings = ProjectSettings(
        site_address=values.get("address", ""),
        country=country,
        region=values.get("state", ""),
        city=values.get("city", ""),
        authority=values.get("planning_authority", ""),
    )
    # City and generic jurisdiction labels never establish an authority. Country is
    # mandatory to prevent same-name matches across national boundaries.
    matches = [
        r.slug
        for r in records
        if settings.country == r.country
        and settings.authority
        and normalized(r.name) == normalized(settings.authority)
    ]
    return Proposal(
        settings=settings,
        matched_slugs=matches,
        conflicts=list(extraction.conflicting_fields),
        notes=[
            "Confirm or correct every field. A mailing city does not establish authority.",
            "OCR is pending; image-only pages require manual entry.",
        ]
        + (
            []
            if matches
            else ["No supported authority record matched. Manual selection is required."]
        ),
    )


def availability(settings: ProjectSettings, records: list[AdoptionRecord]) -> dict[str, object]:
    """Metadata only: this flow does not execute local compliance checks."""
    matches = [
        r
        for r in records
        if r.country == settings.country and normalized(r.name) == normalized(settings.authority)
    ]
    notes: list[str] = []
    chain: list[AdoptionRecord] = []
    if len(matches) == 1:
        by_slug = {r.slug: r for r in records}
        record = matches[0]
        seen: set[str] = set()
        while True:
            if record.slug in seen:
                notes.append("Adoption chain contains a cycle.")
                break
            seen.add(record.slug)
            chain.insert(0, record)
            if record.parent is None:
                break
            if record.parent not in by_slug:
                notes.append("Adoption parent is missing.")
                break
            record = by_slug[record.parent]
        for record in chain:
            if record.missing:
                notes.append(f"{record.name}: missing {', '.join(record.missing)}")
            if (
                settings.permit_date
                and record.effective_date
                and settings.permit_date < record.effective_date
            ):
                notes.append(f"{record.name}: permit predates the recorded edition.")
            if record.country != settings.country:
                notes.append("Adoption chain crosses countries.")
    else:
        notes.append("No unique supported authority adoption record.")
    if not settings.confirmed or not settings.complete:
        notes.append(
            "Confirm country, region, authority and permit date to establish applicability."
        )
    return {
        "status": "not checked",
        "adoption_available": not notes,
        "records": [r.model_dump(mode="json") for r in chain],
        "notes": notes,
    }
