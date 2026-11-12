"""The location providers available, one per country.

Each provider needs an author-approved data source, licence and privacy review before it
is added here. A country missing from this table falls back to the user naming the
authority (``resolve.resolve_address``).
"""

from __future__ import annotations

from plancheck.jurisdiction.census import CensusGeocoder
from plancheck.jurisdiction.resolve import LocationProvider


def default_providers() -> dict[str, LocationProvider]:
    return {"US": CensusGeocoder()}
