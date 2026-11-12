"""U.S. location provider: address lookup with the U.S. Census Bureau geocoder.

The geocoder is a free public service that needs no key. It returns the state, county,
and incorporated place whose boundaries contain an address, which is exactly the
question a jurisdiction lookup has to answer.

Using it sends the site address to the Census Bureau. Callers decide whether to do
that; nothing in this module runs unless ``locate`` is called.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any, Literal

import truststore

from plancheck.jurisdiction.resolve import Authority, Location, census_authority_id

Level = Literal["state", "county", "place"]

URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
SERVICE = "U.S. Census Bureau geocoder (geocoding.geo.census.gov)"
_LAYERS: dict[str, Level] = {
    "States": "state",
    "Counties": "county",
    "Incorporated Places": "place",
}
_ACTIVE = "A"  # FUNCSTAT: an active government, as opposed to a statistical or inactive area


def parse_response(payload: dict[str, Any]) -> Location | None:
    """Turn a geocoder response into a Location. None if the address was not matched."""
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    match = matches[0]
    found: dict[Level, Authority] = {}
    for layer, level in _LAYERS.items():
        for entry in match.get("geographies", {}).get(layer, []):
            # Washington, DC shows why this matters: its "county" and "place" are
            # boundaries with no government of their own.
            if entry.get("FUNCSTAT") == _ACTIVE:
                found[level] = Authority(
                    country="US",
                    level=level,
                    authority_id=census_authority_id(level, entry["GEOID"]),
                    name=entry["NAME"],
                )
                break
    if "state" not in found:
        return None
    authorities = [found[level] for level in ("state", "county", "place") if level in found]
    notes = []
    if "place" not in found:
        notes.append(
            f"The site is not inside an incorporated city, so {authorities[-1].name} is the "
            "likely authority, even if the mailing address names a city."
        )
    return Location(
        country="US",
        matched_address=match["matchedAddress"],
        authorities=authorities,
        notes=notes,
    )


class CensusGeocoder:
    """Looks a U.S. address up over the network."""

    country = "US"
    service = SERVICE

    def __init__(self, timeout_s: float = 30.0) -> None:
        self.timeout_s = timeout_s
        # Use the operating system's certificate store.
        self._tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def locate(self, address: str) -> Location | None:
        query = urllib.parse.urlencode(
            {
                "address": address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            }
        )
        request = urllib.request.Request(f"{URL}?{query}", headers={"User-Agent": "plancheck"})
        with urllib.request.urlopen(request, timeout=self.timeout_s, context=self._tls) as reply:
            return parse_response(json.load(reply))
