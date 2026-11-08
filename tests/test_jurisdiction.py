"""Jurisdiction lookup, tested against saved responses from the Census geocoder.

The fixtures are real responses for four public addresses, trimmed to the layers used.
No test touches the network.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from plancheck.jurisdiction.census import parse_response
from plancheck.jurisdiction.resolve import (
    AdoptionRecord,
    Location,
    load_adoption_records,
    resolve_jurisdiction,
)

FIXTURES = Path(__file__).parent / "fixtures" / "census"


def saved(name: str) -> Location | None:
    return parse_response(json.loads((FIXTURES / f"{name}.json").read_text()))


class SavedGeocoder:
    def __init__(self, name: str) -> None:
        self.name = name

    def locate(self, address: str) -> Location | None:
        return saved(self.name)


def record(slug: str, level: str, geoid: str, **overrides: Any) -> AdoptionRecord:
    """A made-up adoption record. None of these facts describe a real adoption."""
    fields: dict[str, Any] = {
        "name": slug.title(),
        "slug": slug,
        "level": level,
        "geoid": geoid,
        "base_code": "Test Code",
        "base_edition": "1",
        "effective_date": date(2020, 1, 1),
        "adopting_reference": "Test Ord. 1",
        "source_url": "https://example.test/adoption",
        "retrieved_on": date(2026, 11, 5),
        "verified_by": "test",
    }
    return AdoptionRecord(**(fields | overrides))


# ---------------------------------------------------------------- reading the geocoder


def test_address_inside_a_city() -> None:
    location = saved("city_hall_los_angeles")
    assert location is not None
    assert (location.authority.level, location.authority.geoid) == ("place", "0644000")
    assert location.authority.name == "Los Angeles city"
    assert location.county is not None
    assert location.county.geoid == "06037"
    assert location.state.geoid == "06"


def test_mailing_city_is_not_the_jurisdiction() -> None:
    # The address reads "Los Angeles, CA", but the site is in unincorporated county land.
    location = saved("east_la_civic_center")
    assert location is not None
    assert "LOS ANGELES" in location.matched_address
    assert location.place is None
    assert (location.authority.level, location.authority.name) == ("county", "Los Angeles County")


def test_boundaries_without_a_government_are_skipped() -> None:
    # Washington, DC has a "county" and a "place" on the map, neither with a government.
    location = saved("white_house")
    assert location is not None
    assert location.place is None
    assert location.county is None
    assert (location.authority.level, location.authority.name) == ("state", "District of Columbia")


def test_unmatched_address() -> None:
    assert saved("no_match") is None
    assert parse_response({}) is None


# ---------------------------------------------------------------- resolving


def test_city_with_a_record_and_a_state_parent() -> None:
    records = [
        record("ca", "state", "06"),
        record("los-angeles", "place", "0644000", parent="ca"),
    ]
    result = resolve_jurisdiction("x", SavedGeocoder("city_hall_los_angeles"), records)
    assert result.jurisdiction == "los-angeles"
    assert result.chain == ["ca", "los-angeles"]  # state first, so the city amends it
    assert result.rulesets == ["local/ca", "local/los-angeles"]
    assert result.notes[0].startswith("Matched address: 200 S SPRING ST")


def test_unincorporated_site_resolves_to_the_county() -> None:
    records = [
        record("ca", "state", "06"),
        record("los-angeles", "place", "0644000", parent="ca"),
        record("la-county", "county", "06037", parent="ca"),
    ]
    result = resolve_jurisdiction("x", SavedGeocoder("east_la_civic_center"), records)
    assert result.jurisdiction == "la-county"
    assert result.chain == ["ca", "la-county"]
    assert any("not inside an incorporated city" in note for note in result.notes)


def test_no_record_for_the_authority_falls_back_to_the_state() -> None:
    result = resolve_jurisdiction(
        "x", SavedGeocoder("city_hall_los_angeles"), [record("ca", "state", "06")]
    )
    assert result.jurisdiction is None  # the city's own code is not on file
    assert result.chain == ["ca"]  # but the state's rules can still run
    assert any("No adoption record is on file for Los Angeles city" in n for n in result.notes)


def test_no_records_at_all() -> None:
    result = resolve_jurisdiction("x", SavedGeocoder("white_house"), [])
    assert result.authority is not None
    assert result.authority.name == "District of Columbia"
    assert (result.jurisdiction, result.chain, result.rulesets) == (None, [], [])
    assert any("is not checked" in note for note in result.notes)


def test_incomplete_record_is_named_and_not_used() -> None:
    records = [
        record("ca", "state", "06", base_edition=None, verified_by=None),
        record("los-angeles", "place", "0644000", parent="ca"),
    ]
    result = resolve_jurisdiction("x", SavedGeocoder("city_hall_los_angeles"), records)
    # The city amends the state's code, so without a usable state record neither runs.
    assert (result.jurisdiction, result.chain) == (None, [])
    assert any("incomplete (base_edition, verified_by)" in note for note in result.notes)


def test_unmatched_address_asks_for_manual_entry() -> None:
    result = resolve_jurisdiction("nowhere", SavedGeocoder("no_match"), [])
    assert (result.location, result.authority, result.jurisdiction) == (None, None, None)
    assert result.notes == ["The address could not be matched. Enter the jurisdiction by hand."]


def test_every_resolution_warns_about_special_authorities() -> None:
    result = resolve_jurisdiction("x", SavedGeocoder("white_house"), [])
    assert "state-owned buildings" in result.notes[-1]


# ---------------------------------------------------------------- records on disk


def test_shipped_config_has_only_the_template() -> None:
    # No adoption facts are shipped until someone verifies them against a source.
    assert load_adoption_records() == []


def write_record(folder: Path, rec: AdoptionRecord) -> None:
    (folder / f"{rec.slug}.yaml").write_text(yaml.safe_dump(rec.model_dump(mode="json")))


def test_records_load_from_a_folder(tmp_path: Path) -> None:
    write_record(tmp_path, record("ca", "state", "06"))
    write_record(tmp_path, record("los-angeles", "place", "0644000", parent="ca"))
    (tmp_path / "_template.yaml").write_text("name: null\n")
    assert [r.slug for r in load_adoption_records(tmp_path)] == ["ca", "los-angeles"]


def test_record_with_an_unknown_parent_is_rejected(tmp_path: Path) -> None:
    write_record(tmp_path, record("los-angeles", "place", "0644000", parent="ca"))
    with pytest.raises(ValueError, match="parent 'ca' has no record"):
        load_adoption_records(tmp_path)


def test_record_slug_must_match_its_file_name(tmp_path: Path) -> None:
    (tmp_path / "wrong.yaml").write_text(
        yaml.safe_dump(record("ca", "state", "06").model_dump(mode="json"))
    )
    with pytest.raises(ValueError, match="does not match the file name"):
        load_adoption_records(tmp_path)
