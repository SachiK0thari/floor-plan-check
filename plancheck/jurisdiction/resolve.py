"""From a site address to the government whose building code applies.

Two facts make this harder than reading the city off the address:

- **A mailing city is not a jurisdiction.** An address can say "Los Angeles" and sit in
  unincorporated county land, where the county is the authority. So the lookup geocodes
  the address and asks which government boundaries the point falls inside.
- **Adoption is layered.** A city usually amends a code the state adopted. A resolved
  jurisdiction is therefore a chain of adoption records, from the state down.

The result is a proposal. It names the matched address and the authority found, so the
user can confirm or correct it, and it never invents an adoption fact: if no adoption
record is on file for the authority, it says so and no local rules run.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field

from plancheck.config import config_dir

Level = Literal["state", "county", "place"]

_ALWAYS_NOTE = (
    "Some projects answer to a different authority whatever the address: state-owned "
    "buildings, public schools, hospitals, and federal or tribal land. Confirm the authority."
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Authority(_Base):
    """A government that can adopt a building code."""

    level: Level
    geoid: str
    name: str


class Location(_Base):
    """What a geocoder found for an address: the governments whose boundaries contain it.

    ``county`` and ``place`` are set only when an active government exists at that level.
    """

    matched_address: str
    state: Authority
    county: Authority | None = None
    place: Authority | None = None

    @property
    def authority(self) -> Authority:
        """The most local active government: the city if the site is inside one."""
        return self.place or self.county or self.state


class Geocoder(Protocol):
    def locate(self, address: str) -> Location | None:
        """The location of an address, or None if the address cannot be matched."""
        ...


class AdoptionRecord(_Base):
    """One jurisdiction's code adoption, from ``configs/jurisdictions/<slug>.yaml``."""

    name: str
    slug: str
    level: Level
    geoid: str | None = None
    country: str = "US"
    authority_id: str | None = None
    parent: str | None = None
    base_code: str | None = None
    base_edition: str | None = None
    effective_date: date | None = None
    adopting_reference: str | None = None
    source_url: str | None = None
    retrieved_on: date | None = None
    verified_by: str | None = None

    @property
    def missing(self) -> list[str]:
        """Adoption facts not yet filled in. A record with any of these does not run."""
        required = (
            "base_code",
            "base_edition",
            "effective_date",
            "adopting_reference",
            "source_url",
            "retrieved_on",
            "verified_by",
        )
        missing = [
            name
            for name in required
            if getattr(self, name) is None
            or (isinstance(getattr(self, name), str) and not getattr(self, name).strip())
        ]
        identifier = "geoid" if self.country == "US" else "authority_id"
        if not getattr(self, identifier):
            missing.append(identifier)
        return missing


def load_adoption_records(folder: Path | None = None) -> list[AdoptionRecord]:
    """Every adoption record on file. Files whose names start with ``_`` are templates."""
    folder = folder or config_dir() / "jurisdictions"
    records = []
    for path in sorted(folder.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        record = AdoptionRecord.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if record.slug != path.stem:
            raise ValueError(f"{path}: slug '{record.slug}' does not match the file name")
        records.append(record)
    slugs = {record.slug for record in records}
    for record in records:
        if record.parent is not None and record.parent not in slugs:
            raise ValueError(f"{record.slug}: parent '{record.parent}' has no record")
    return records


class Resolution(_Base):
    """A proposed jurisdiction for a site, for the user to confirm."""

    address: str
    location: Location | None
    authority: Authority | None
    jurisdiction: str | None  # slug of the authority's adoption record, if one is usable
    chain: list[str] = Field(default_factory=list)  # usable records, from the state down
    notes: list[str] = Field(default_factory=list)

    @property
    def rulesets(self) -> list[str]:
        """Local rulesets to layer over the base rules, in order."""
        return [f"local/{slug}" for slug in self.chain]


def _chain(record: AdoptionRecord, by_slug: dict[str, AdoptionRecord]) -> list[AdoptionRecord]:
    chain = [record]
    while chain[0].parent is not None:
        parent = by_slug[chain[0].parent]
        if parent in chain:
            raise ValueError(f"adoption records form a loop at '{parent.slug}'")
        chain.insert(0, parent)
    return chain


def resolve_jurisdiction(
    address: str, geocoder: Geocoder, records: list[AdoptionRecord]
) -> Resolution:
    """Propose the jurisdiction for a site address."""
    location = geocoder.locate(address)
    if location is None:
        return Resolution(
            address=address,
            location=None,
            authority=None,
            jurisdiction=None,
            notes=["The address could not be matched. Enter the jurisdiction by hand."],
        )
    authority = location.authority
    notes = [f"Matched address: {location.matched_address}. Check that it is the site."]
    if location.place is None:
        notes.append(
            f"The site is not inside an incorporated city, so {authority.name} is the "
            "likely authority, even if the mailing address names a city."
        )

    by_slug = {record.slug: record for record in records}
    by_key = {
        (record.level, record.geoid): record
        for record in records
        if record.country == "US" and record.geoid is not None
    }
    record = by_key.get((authority.level, authority.geoid))
    # With no record for the local authority, a state record may still apply on its own.
    start = record or by_key.get(("state", location.state.geoid))
    chain = _chain(start, by_slug) if start is not None else []
    usable = []
    for link in chain:
        if link.missing:
            notes.append(
                f"The adoption record for {link.name} is incomplete ({', '.join(link.missing)}),"
                " so its rules are not run."
            )
            break  # rules that amend an unusable parent cannot be layered on it
        usable.append(link.slug)
    if record is None:
        notes.append(
            f"No adoption record is on file for {authority.name}. "
            "Its local building code is not checked."
        )
    notes.append(_ALWAYS_NOTE)
    jurisdiction = record.slug if record is not None and record.slug in usable else None
    return Resolution(
        address=address,
        location=location,
        authority=authority,
        jurisdiction=jurisdiction,
        chain=usable,
        notes=notes,
    )
