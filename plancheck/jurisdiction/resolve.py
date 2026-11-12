"""From a site location to the government whose building code applies, in any country.

Two facts make this harder than reading the city off the address:

- **A mailing city is not a jurisdiction.** An address can say "Los Angeles" and sit in
  unincorporated county land, where the county is the authority. So a location provider
  asks which government boundaries the site falls inside.
- **Adoption is layered.** A city usually amends a code its state or nation adopted. A
  resolved jurisdiction is therefore a chain of adoption records, broadest first.

No country is special here. Each country that supports lookup has a ``LocationProvider``
(the U.S. Census geocoder is the first); a country without one falls back to the user
naming the authority. Authorities and adoption records are matched by
``(country, authority_id)``, so adding an authority anywhere means adding a record and a
ruleset, never changing this module.

The result is a proposal. It names the matched address and the authority found, so the
user can confirm or correct it, and it never invents an adoption fact: if no adoption
record is on file for the authority, it says so and no local rules run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Protocol

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from plancheck.config import config_dir

_ALWAYS_NOTE = (
    "Some projects answer to a different authority whatever the address: state-owned "
    "buildings, public schools, hospitals, and federal or tribal land. Confirm the authority."
)
_COUNTRY = re.compile(r"^[A-Z]{2}$")


def census_authority_id(level: str, geoid: str) -> str:
    """The ``authority_id`` of a U.S. government identified by Census level and GEOID."""
    return f"census:{level}:{geoid}"


def _country(value: str) -> str:
    value = value.strip().upper()
    if not _COUNTRY.match(value):
        raise ValueError(f"country must be an ISO 3166-1 alpha-2 code, not {value!r}")
    return value


Country = Annotated[str, AfterValidator(_country)]


def normalized_name(value: str) -> str:
    """A name compared case- and punctuation-insensitively."""
    return re.sub(r"\W+", " ", value.casefold()).strip()


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Authority(_Base):
    """A government that can adopt a building code, as a location provider identifies it.

    ``authority_id`` is stable and unique within ``country``; ``level`` uses the provider's
    own vocabulary (for example state, county, place, or district).
    """

    country: Country
    level: str
    authority_id: str
    name: str


class Location(_Base):
    """What a provider found for a site: the governments whose boundaries contain it.

    ``authorities`` lists only governments with authority, broadest first, so the last
    entry is the most local one. ``notes`` carries provider-specific caveats.
    """

    country: Country
    matched_address: str
    authorities: list[Authority] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _same_country(self) -> Location:
        if any(a.country != self.country for a in self.authorities):
            raise ValueError("every authority in a location must be in its country")
        return self

    @property
    def authority(self) -> Authority:
        """The most local government, such as the city if the site is inside one."""
        return self.authorities[-1]

    @property
    def root(self) -> Authority:
        """The broadest government found, such as the state."""
        return self.authorities[0]

    def at(self, level: str) -> Authority | None:
        return next((a for a in self.authorities if a.level == level), None)


class Geocoder(Protocol):
    def locate(self, address: str) -> Location | None:
        """The location of an address, or None if the address cannot be matched."""
        ...


class LocationProvider(Geocoder, Protocol):
    """A per-country lookup. Calling ``locate`` sends the address to ``service``."""

    country: str
    service: str


class AdoptionRecord(_Base):
    """One jurisdiction's code adoption, from ``configs/jurisdictions/<slug>.yaml``.

    ``(country, authority_id)`` identifies the authority in every country. For U.S.
    records, ``level`` and ``geoid`` may be given instead of ``authority_id``; the two
    forms name the same identifier (``census:<level>:<geoid>``).
    """

    name: str
    slug: str
    country: Country
    level: str
    authority_id: str | None = None
    geoid: str | None = None
    parent: str | None = None
    base_code: str | None = None
    base_edition: str | None = None
    effective_date: date | None = None
    adopting_reference: str | None = None
    source_url: str | None = None
    retrieved_on: date | None = None
    verified_by: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_census_record(cls, data: object) -> object:
        # Records saved before ``country`` was required defaulted to the U.S.; only U.S.
        # Census records carry a geoid, so that is the one case where it can be inferred.
        if isinstance(data, dict) and "country" not in data and data.get("geoid"):
            return {**data, "country": "US"}
        return data

    @model_validator(mode="after")
    def _identifiers_agree(self) -> AdoptionRecord:
        if self.geoid is None:
            return self
        if self.country != "US":
            raise ValueError(f"{self.slug}: geoid is a U.S. Census identifier; use authority_id")
        if self.authority_id not in (None, census_authority_id(self.level, self.geoid)):
            raise ValueError(f"{self.slug}: authority_id and geoid name different authorities")
        return self

    @property
    def identity(self) -> str | None:
        """The authority identifier this record matches, if it has one."""
        if self.authority_id:
            return self.authority_id
        if self.geoid:
            return census_authority_id(self.level, self.geoid)
        return None

    @property
    def key(self) -> tuple[str, str] | None:
        return None if self.identity is None else (self.country, self.identity)

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
        if self.identity is None:
            missing.append("authority_id")
        return missing


def check_records(records: list[AdoptionRecord]) -> None:
    """Reject records that cannot be matched or layered unambiguously."""
    by_slug: dict[str, AdoptionRecord] = {}
    by_key: dict[tuple[str, str], str] = {}
    for record in records:
        if record.slug in by_slug:
            raise ValueError(f"two adoption records use the slug '{record.slug}'")
        by_slug[record.slug] = record
        if record.key is not None:
            if record.key in by_key:
                raise ValueError(
                    f"{record.slug}: {record.key[1]} in {record.key[0]} already belongs to "
                    f"'{by_key[record.key]}'"
                )
            by_key[record.key] = record.slug
    for record in records:
        if record.parent is None:
            continue
        parent = by_slug.get(record.parent)
        if parent is None:
            raise ValueError(f"{record.slug}: parent '{record.parent}' has no record")
        if parent.country != record.country:
            raise ValueError(
                f"{record.slug}: parent '{parent.slug}' is in {parent.country}, "
                f"not {record.country}"
            )


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
    check_records(records)
    return records


def records_named(country: str, name: str, records: list[AdoptionRecord]) -> list[AdoptionRecord]:
    """Records whose authority name matches a user-named authority in that country.

    Country is mandatory, so same-name authorities in different countries never match.
    """
    if not country or not name.strip():
        return []
    country = country.strip().upper()
    return [
        r
        for r in records
        if r.country == country and normalized_name(r.name) == normalized_name(name)
    ]


class Resolution(_Base):
    """A proposed jurisdiction for a site, for the user to confirm."""

    address: str
    location: Location | None
    authority: Authority | None
    jurisdiction: str | None  # slug of the authority's adoption record, if one is usable
    chain: list[str] = Field(default_factory=list)  # usable records, broadest first
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
        if parent.country != record.country:
            raise ValueError(f"adoption chain of '{record.slug}' crosses countries")
        chain.insert(0, parent)
    return chain


def resolve_jurisdiction(
    address: str, geocoder: Geocoder, records: list[AdoptionRecord]
) -> Resolution:
    """Propose the jurisdiction for a site address with one location provider."""
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
    notes.extend(location.notes)

    by_slug = {record.slug: record for record in records}
    by_key = {record.key: record for record in records if record.key is not None}
    record = by_key.get((location.country, authority.authority_id))
    # With no record for the local authority, the broadest one may still apply on its own.
    start = record or by_key.get((location.country, location.root.authority_id))
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


def resolve_address(
    country: str,
    address: str,
    providers: Mapping[str, LocationProvider],
    records: list[AdoptionRecord],
) -> Resolution:
    """Resolve with the provider for ``country``; without one, ask for the authority.

    Only call this on an explicit user action: the address goes to the provider's service.
    """
    country = _country(country)
    provider = providers.get(country)
    if provider is None:
        return Resolution(
            address=address,
            location=None,
            authority=None,
            jurisdiction=None,
            notes=[
                f"No location lookup is available for {country}. "
                "Name the responsible authority to continue."
            ],
        )
    if provider.country != country:
        raise ValueError(f"provider for {country} serves {provider.country}")
    return resolve_jurisdiction(address, provider, records)
