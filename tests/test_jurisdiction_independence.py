"""The engine does not depend on any one jurisdiction or country (PRD M2 step 7).

Two synthetic authorities in different countries are added purely as data: an adoption
record chain under a configs folder and a local ruleset under a rules folder. Nothing in
``plancheck`` changes between them. None of these facts describes a real adoption or a
real requirement.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from plancheck.compliance.engine import Report, run
from plancheck.compliance.registry import RULES_DIR, resolve
from plancheck.compliance.verdict import Verdict
from plancheck.jurisdiction.resolve import (
    AdoptionRecord,
    Authority,
    Location,
    load_adoption_records,
    records_named,
    resolve_address,
)
from plancheck.model.types import BuildingModel, ProjectContext
from tests.conftest import exact
from tests.test_multi_code import width_rule
from tests.test_rules import write_rules

FACTS: dict[str, Any] = {
    "base_code": "Synthetic Building Code (not law)",
    "base_edition": "test-1",
    "effective_date": "2010-01-01",
    "adopting_reference": "TEST ONLY",
    "source_url": "https://example.test/adoption",
    "retrieved_on": "2026-11-12",
    "verified_by": "Synthetic fixture, not verified legal facts",
}

# Two chains, broadest first. The U.S. one uses Census identifiers; the New Zealand one
# uses an application-assigned authority_id. Both are matched the same way.
RECORDS: list[dict[str, Any]] = [
    {"name": "Test State", "slug": "test-us-state", "country": "US", "level": "state",
     "geoid": "99"},
    {"name": "Test City", "slug": "test-us-city", "country": "US", "level": "place",
     "geoid": "9900001", "parent": "test-us-state"},
    {"name": "Test Region", "slug": "test-nz-region", "country": "NZ", "level": "region",
     "authority_id": "synthetic:nz:region-1"},
    {"name": "Test District Council", "slug": "test-nz-district", "country": "NZ",
     "level": "district", "authority_id": "synthetic:nz:district-1",
     "parent": "test-nz-region"},
]  # fmt: skip

# Each authority adds its own door-width requirement (synthetic values).
LOCAL_WIDTH_MM = {"test-us-city": 900, "test-nz-district": 1000}


def write_records(folder: Path, records: list[dict[str, Any]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for data in records:
        (folder / f"{data['slug']}.yaml").write_text(yaml.safe_dump(FACTS | data))


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    write_records(tmp_path / "jurisdictions", RECORDS)
    return tmp_path / "jurisdictions"


@pytest.fixture
def rules_root(tmp_path: Path) -> Path:
    root = tmp_path / "rules"
    shutil.copytree(RULES_DIR / "ada_2010", root / "ada_2010")
    for slug, width in LOCAL_WIDTH_MM.items():
        rule = width_rule(
            f"{slug}.door-width",
            jurisdiction=slug,
            requirement={"min_clear_width": {"value": width, "unit": "mm"}},
        )
        write_rules(root, f"local/{slug}", rule)
    return root


def project_model(model: BuildingModel, jurisdiction: str, country: str) -> BuildingModel:
    return model.model_copy(
        update={
            "project": ProjectContext(
                country=country,
                facility_type="commercial_facility",
                work_type="new",
                permit_date=date(2026, 1, 1),
                jurisdiction=jurisdiction,
                jurisdiction_source="user",
            ),
            "openings": [
                o.model_copy(update={"clear_width": exact(950)}) if o.kind == "door" else o
                for o in model.openings
            ],
        }
    )


def door_verdicts(report: Report, door: str = "D1") -> dict[str, Verdict]:
    return {f.rule_id: f.verdict for f in report.for_element(door)}


@pytest.mark.parametrize(
    ("jurisdiction", "country", "active", "verdict"),
    [
        # 950 mm passes the 900 mm U.S. city rule.
        ("test-us-city", "US", "test-us-city", Verdict.PASS),
        # 950 mm fails the 1000 mm NZ district rule.
        ("test-nz-district", "NZ", "test-nz-district", Verdict.FAIL),
    ],
)
def test_local_rules_run_for_an_authority_in_any_country(
    two_rooms: BuildingModel,
    configs: Path,
    rules_root: Path,
    jurisdiction: str,
    country: str,
    active: str,
    verdict: Verdict,
) -> None:
    records = load_adoption_records(configs)
    resolved = resolve(["ada_2010", *(f"local/{slug}" for slug in LOCAL_WIDTH_MM)], rules_root)
    report = run(
        project_model(two_rooms, jurisdiction, country), resolved, adoption_records=records
    )
    verdicts = door_verdicts(report)
    assert verdicts[f"{active}.door-width"] is verdict
    # The other country's rules are loaded but never applied to this project.
    (other,) = set(LOCAL_WIDTH_MM) - {active}
    findings = report.for_rule(f"{other}.door-width")
    assert findings
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in findings)
    assert all("outside the selected jurisdiction chain" in (f.reason or "") for f in findings)
    # The ADA reference result is the same whichever authority the project is under.
    assert verdicts["ada2010.door-clear-width"] is Verdict.PASS


class FakeProvider:
    """A per-country location provider answering from a fixed location."""

    def __init__(self, country: str, location: Location | None) -> None:
        self.country = country
        self.service = f"synthetic {country} lookup (test only)"
        self.location = location
        self.calls: list[str] = []

    def locate(self, address: str) -> Location | None:
        self.calls.append(address)
        return self.location


def nz_location() -> Location:
    return Location(
        country="NZ",
        matched_address="1 Test Street, Test District",
        authorities=[
            Authority(country="NZ", level="region", authority_id="synthetic:nz:region-1",
                      name="Test Region"),
            Authority(country="NZ", level="district", authority_id="synthetic:nz:district-1",
                      name="Test District Council"),
        ],
    )  # fmt: skip


def test_each_country_resolves_through_its_own_provider(configs: Path) -> None:
    records = load_adoption_records(configs)
    nz = FakeProvider("NZ", nz_location())
    us = FakeProvider("US", None)
    result = resolve_address("nz", "1 Test Street", {"NZ": nz, "US": us}, records)
    assert result.jurisdiction == "test-nz-district"
    assert result.chain == ["test-nz-region", "test-nz-district"]
    assert result.rulesets == ["local/test-nz-region", "local/test-nz-district"]
    assert (nz.calls, us.calls) == (["1 Test Street"], [])


def test_country_without_a_provider_asks_for_the_authority(configs: Path) -> None:
    records = load_adoption_records(configs)
    us = FakeProvider("US", None)
    result = resolve_address("NZ", "1 Test Street", {"US": us}, records)
    assert (result.location, result.jurisdiction, us.calls) == (None, None, [])
    assert result.notes == [
        "No location lookup is available for NZ. Name the responsible authority to continue."
    ]
    # The user-named fallback finds the record by name, within the country only.
    assert [r.slug for r in records_named("NZ", "test district council", records)] == [
        "test-nz-district"
    ]
    assert records_named("US", "Test District Council", records) == []


def test_same_identifier_in_two_countries_does_not_collide(tmp_path: Path) -> None:
    shared = {"level": "district", "authority_id": "synthetic:shared"}
    write_records(
        tmp_path,
        [
            {"name": "A", "slug": "a", "country": "NZ"} | shared,
            {"name": "B", "slug": "b", "country": "IE"} | shared,
        ],
    )
    assert {r.key for r in load_adoption_records(tmp_path)} == {
        ("NZ", "synthetic:shared"),
        ("IE", "synthetic:shared"),
    }


def test_two_records_for_one_authority_are_rejected(tmp_path: Path) -> None:
    write_records(
        tmp_path,
        [
            {"name": "A", "slug": "a", "country": "US", "level": "place", "geoid": "1"},
            {"name": "B", "slug": "b", "country": "US", "level": "place",
             "authority_id": "census:place:1"},
        ],
    )  # fmt: skip
    with pytest.raises(ValueError, match="already belongs to 'a'"):
        load_adoption_records(tmp_path)


def test_adoption_chain_cannot_cross_countries(tmp_path: Path) -> None:
    write_records(
        tmp_path,
        [
            {"name": "Parent", "slug": "parent", "country": "US", "level": "state",
             "geoid": "99"},
            {"name": "Child", "slug": "child", "country": "NZ", "level": "district",
             "authority_id": "synthetic:child", "parent": "parent"},
        ],
    )  # fmt: skip
    with pytest.raises(ValueError, match="is in US, not NZ"):
        load_adoption_records(tmp_path)


def test_census_identifiers_are_us_only_and_must_agree() -> None:
    base: dict[str, Any] = {"name": "X", "slug": "x", "level": "place"}
    with pytest.raises(ValueError, match=r"geoid is a U\.S\. Census identifier"):
        AdoptionRecord(**base, country="NZ", geoid="1")
    with pytest.raises(ValueError, match="name different authorities"):
        AdoptionRecord(**base, country="US", geoid="1", authority_id="census:place:2")
    with pytest.raises(ValueError, match="ISO 3166-1 alpha-2"):
        AdoptionRecord(**base, country="India", authority_id="x")
    assert AdoptionRecord(**base, country="us", geoid="1").key == ("US", "census:place:1")


def test_record_without_country_needs_a_census_geoid() -> None:
    # Records saved before country was required were U.S. Census records.
    legacy = AdoptionRecord.model_validate({"name": "X", "slug": "x", "level": "place",
                                            "geoid": "1"})  # fmt: skip
    assert legacy.country == "US"
    with pytest.raises(ValueError, match="country"):
        AdoptionRecord.model_validate({"name": "X", "slug": "x", "level": "place"})
