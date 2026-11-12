"""Synthetic code/adoption facts only: no fixture is a real local requirement."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from plancheck.compliance.context import CheckContext
from plancheck.compliance.engine import Report, run
from plancheck.compliance.registry import RULES_DIR, ResolvedRules, load_ruleset, resolve
from plancheck.compliance.results import CheckOutcome, MeasurementSemantics
from plancheck.compliance.verdict import Verdict, decide_min
from plancheck.jurisdiction.resolve import AdoptionRecord
from plancheck.model.types import BuildingModel, Measured, ProjectContext
from tests.conftest import exact
from tests.test_rules import write_rules

CODE = "Synthetic Building Code (not law)"
EDITION = "test-1"
SLUG = "test-city"


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    shutil.copytree(RULES_DIR / "ada_2010", tmp_path / "ada_2010")
    return tmp_path


def width_rule(rule_id: str = "test.local-width", **updates: Any) -> dict[str, Any]:
    original = next(
        r.rule for r in load_ruleset("ada_2010") if r.rule.check == "opening_clear_width"
    )
    data = original.model_dump(mode="json")
    data.update(
        id=rule_id,
        code=CODE,
        edition=EDITION,
        section="TEST-WIDTH",
        jurisdiction=SLUG,
        source_url="https://example.test/local-width",
        source_text=None,
        verified_by="Synthetic test fixture only",
        exceptions=[],
        effective_date="2020-01-01",
        selection={"element": "opening", "filter": {"kind": ["door"]}},
        requirement={"min_clear_width": {"value": 900, "unit": "mm"}},
    )
    return data | updates


@pytest.fixture
def records() -> list[AdoptionRecord]:
    return [
        AdoptionRecord(
            name="Synthetic authority (not a real adoption)",
            slug=SLUG,
            country="US",
            level="place",
            geoid="TEST",
            base_code=CODE,
            base_edition=EDITION,
            effective_date=date(2010, 1, 1),
            adopting_reference="TEST ONLY",
            source_url="https://example.test/adoption",
            retrieved_on=date(2026, 1, 1),
            verified_by="Synthetic fixture, not verified legal facts",
        )
    ]


@pytest.fixture
def model(two_rooms: BuildingModel) -> BuildingModel:
    return two_rooms.model_copy(
        update={
            "project": ProjectContext(
                facility_type="commercial_facility",
                work_type="new",
                permit_date=date(2026, 1, 1),
                jurisdiction=SLUG,
                jurisdiction_source="user",
            ),
            "openings": [
                o.model_copy(update={"clear_width": exact(850)}) if o.kind == "door" else o
                for o in two_rooms.openings
            ],
        }
    )


def resolved_width(root: Path, **updates: Any) -> ResolvedRules:
    write_rules(root, f"local/{SLUG}", width_rule(**updates))
    return resolve(["ada_2010", f"local/{SLUG}"], root)


def widths(report: Report, door: str = "D1") -> dict[str, Verdict]:
    return {
        f.rule_id: f.verdict
        for f in report.for_element(door)
        if f.rule_id in ("ada2010.door-clear-width", "test.local-width", "test.base-width")
    }


def test_stricter_local_preserves_both_findings_and_citations(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    report = run(model, resolved_width(rules_dir), adoption_records=records)
    assert widths(report) == {
        "ada2010.door-clear-width": Verdict.PASS,
        "test.local-width": Verdict.FAIL,
    }
    governing = next(g for g in report.governing_requirements if g.element_id == "D1")
    assert governing.required_mm == 900
    assert governing.governing_rule_ids == ["test.local-width"]
    assert governing.quantity == "opening.clear_width"
    sources = {f.rule_id: f for f in governing.source_findings}
    assert sources["ada2010.door-clear-width"].required == "32 in"
    assert sources["test.local-width"].required == "900 mm"
    for finding in sources.values():
        assert finding in report.findings
        assert finding.citation is not None
        assert finding.citation.section == finding.section
        assert finding.citation.source_url
        assert finding.citation.edition
    assert report.for_regime("ada")
    assert report.for_regime("building_code")
    assert all(f.regime == "ada" for f in report.for_regime("ada"))
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored == report


@pytest.mark.parametrize(
    ("value", "winner"), [(800, "ada2010.door-clear-width"), (950, "test.local-width")]
)
def test_governing_selects_strictest_normalized_minimum(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], value: int, winner: str
) -> None:
    report = run(
        model,
        resolved_width(rules_dir, requirement={"min_clear_width": {"value": value, "unit": "mm"}}),
        adoption_records=records,
    )
    assert all(g.governing_rule_ids == [winner] for g in report.governing_requirements)
    assert len(report.governing_requirements) == 2


def test_equal_requirements_preserve_both_sources(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    report = run(
        model,
        resolved_width(rules_dir, requirement={"min_clear_width": {"value": 812.8, "unit": "mm"}}),
        adoption_records=records,
    )
    assert all(
        g.governing_rule_ids == ["ada2010.door-clear-width", "test.local-width"]
        for g in report.governing_requirements
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"effective_date": "2027-01-01"},
        {"superseded_date": "2026-01-01"},
        {"applicability": {"work_type": ["alteration"]}},
    ],
)
def test_inapplicable_local_does_not_govern(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], changes: dict[str, Any]
) -> None:
    report = run(model, resolved_width(rules_dir, **changes), adoption_records=records)
    assert report.governing_requirements == []
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in report.for_rule("test.local-width"))
    assert report.for_rule("ada2010.door-clear-width")


def test_unknown_local_applicability_blocks_comparison(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    report = run(
        model,
        resolved_width(rules_dir, applicability={"occupancy": ["TEST"]}),
        adoption_records=records,
    )
    assert report.governing_requirements == []
    assert report.governing_not_derived
    assert all("unresolved" in item.reason for item in report.governing_not_derived)
    assert widths(report)["ada2010.door-clear-width"] is Verdict.PASS


def test_missing_date_does_not_create_governing_requirement(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    model = model.model_copy(
        update={"project": model.project.model_copy(update={"permit_date": None})}
    )
    report = run(model, resolved_width(rules_dir), adoption_records=records)
    assert report.governing_requirements == []
    assert all(f.verdict is Verdict.UNKNOWN for f in report.findings)


def test_unknown_measurement_does_not_create_governing_requirement(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    model = model.model_copy(
        update={
            "openings": [
                o.model_copy(update={"clear_width": None}) if o.kind == "door" else o
                for o in model.openings
            ]
        }
    )
    report = run(
        model,
        resolved_width(rules_dir),
        CheckContext(clear_width_deductions={}),
        adoption_records=records,
    )
    assert report.governing_requirements == []
    assert report.governing_not_derived


def test_uncertainty_does_not_prevent_comparing_known_requirements(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    model = model.model_copy(
        update={
            "openings": [
                o.model_copy(
                    update={"clear_width": Measured(value_mm=900, sigma_mm=10, source="geometry")}
                )
                if o.kind == "door"
                else o
                for o in model.openings
            ]
        }
    )
    report = run(model, resolved_width(rules_dir), adoption_records=records)
    assert widths(report)["test.local-width"] is Verdict.BORDERLINE
    assert all(g.required_mm == 900 for g in report.governing_requirements)


def test_effective_exception_requirement_is_used(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    model = model.model_copy(
        update={
            "walls": [
                w.model_copy(update={"thickness": exact(700)}) if w.id == "W5" else w
                for w in model.walls
            ]
        }
    )
    report = run(model, resolved_width(rules_dir), adoption_records=records)
    governing = next(g for g in report.governing_requirements if g.element_id == "D1")
    assert governing.governing_rule_ids == ["ada2010.door-clear-width"]
    assert governing.required_mm == pytest.approx(914.4)


@pytest.mark.parametrize("condition", ["alteration", "depth", "draft"])
def test_unresolved_exceptions_or_unverified_rules_do_not_govern(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], condition: str
) -> None:
    updates = {}
    if condition == "alteration":
        model = model.model_copy(
            update={"project": model.project.model_copy(update={"work_type": "alteration"})}
        )
    elif condition == "depth":
        model = model.model_copy(
            update={
                "walls": [
                    w.model_copy(
                        update={
                            "thickness": Measured(value_mm=609.6, sigma_mm=10, source="geometry")
                        }
                    )
                    for w in model.walls
                ]
            }
        )
    else:
        updates = {"status": "draft"}
    report = run(model, resolved_width(rules_dir, **updates), adoption_records=records)
    assert report.governing_requirements == []
    assert report.governing_not_derived


@pytest.mark.parametrize("problem", ["basis", "direction", "measurement"])
def test_incompatible_measurement_semantics_are_not_compared(
    model: BuildingModel,
    rules_dir: Path,
    records: list[AdoptionRecord],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    from plancheck.compliance.checks import CHECK_FUNCTIONS
    from plancheck.compliance.rules import Rule
    from plancheck.model.types import Opening

    def synthetic_check(
        model: BuildingModel, rule: Rule, opening: Opening, ctx: CheckContext
    ) -> CheckOutcome:
        value = opening.clear_width
        assert value is not None
        if problem == "measurement":
            value = value.model_copy(update={"value_mm": value.value_mm + 1})
        return CheckOutcome(
            verdict=decide_min(value, 900, ctx.k),
            measured=value,
            required="900 mm",
            required_mm=900,
            semantics=MeasurementSemantics(
                quantity="opening.clear_width",
                basis="nominal_leaf" if problem == "basis" else "clear_opening",
                relation="max" if problem == "direction" else "min",
            ),
        )

    monkeypatch.setitem(CHECK_FUNCTIONS, "synthetic_width", synthetic_check)
    report = run(
        model, resolved_width(rules_dir, check="synthetic_width"), adoption_records=records
    )
    assert report.governing_requirements == []
    assert len(report.governing_not_derived) == 2


def test_missing_adoption_data_does_not_activate_local_rules(
    model: BuildingModel, rules_dir: Path
) -> None:
    report = run(model, resolved_width(rules_dir), adoption_records=[])
    assert report.governing_requirements == []
    local = report.for_rule("test.local-width")
    assert len(local) == 1
    assert local[0].verdict is Verdict.UNKNOWN
    assert "adoption record missing" in (local[0].reason or "")


def base_and_amendment(root: Path, mode: str, **updates: Any) -> ResolvedRules:
    write_rules(root, "ibc_style", width_rule("test.base-width", jurisdiction=None))
    amendment = width_rule(
        amends={"rule": "test.base-width", "mode": mode},
        effective_date="2024-01-01",
        requirement={"min_clear_width": {"value": 1000, "unit": "mm"}},
    )
    if mode == "delete":
        amendment.update(check=None, requirement={}, proves=None)
    amendment.update(updates)
    write_rules(root, f"local/{SLUG}", amendment)
    return resolve(["ada_2010", "ibc_style", f"local/{SLUG}"], root)


@pytest.mark.parametrize("mode", ["replace", "delete"])
@pytest.mark.parametrize("when", [date(2023, 1, 1), date(2024, 1, 1), date(2026, 1, 1)])
def test_amendments_respect_dates_and_preserve_source_audit(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], mode: str, when: date
) -> None:
    model = model.model_copy(
        update={"project": model.project.model_copy(update={"permit_date": when})}
    )
    report = run(model, base_and_amendment(rules_dir, mode), adoption_records=records)
    applied = when >= date(2024, 1, 1)
    assert len(report.amendments) == 1
    audit = report.amendments[0]
    assert audit.status == ("applied" if applied else "not_applicable")
    assert audit.amended_rule.id == "test.base-width"
    assert audit.amended_rule.source_url
    assert audit.amending_rule.source_url
    assert audit.amended_sha256
    assert audit.amending_sha256
    assert report.for_rule("ada2010.door-clear-width")
    if not applied:
        assert widths(report)["test.base-width"] is Verdict.FAIL
        assert all(g.required_mm == 900 for g in report.governing_requirements)
    elif mode == "replace":
        assert report.for_rule("test.base-width") == []
        assert all(g.required_mm == 1000 for g in report.governing_requirements)
        assert len(report.governing_requirements) == 2
    else:
        assert report.for_rule("test.base-width") == []
        assert report.governing_requirements == []
    assert Report.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize("mode", ["replace", "delete"])
def test_superseded_amendment_restores_base(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], mode: str
) -> None:
    report = run(
        model,
        base_and_amendment(rules_dir, mode, superseded_date="2026-01-01"),
        adoption_records=records,
    )
    assert report.amendments[0].status == "not_applicable"
    assert all(g.required_mm == 900 for g in report.governing_requirements)
    assert len(report.governing_requirements) == 2


@pytest.mark.parametrize("mode", ["replace", "delete"])
def test_unknown_amendment_applicability_does_not_fall_back_to_base(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], mode: str
) -> None:
    resolved = base_and_amendment(rules_dir, mode, applicability={"occupancy": ["TEST"]})
    report = run(model, resolved, adoption_records=records)
    assert report.amendments[0].status == "unknown"
    assert report.for_rule("test.base-width") == []
    assert report.governing_requirements == []
    assert any(f.verdict is Verdict.UNKNOWN for f in report.for_rule("test.local-width"))


@pytest.mark.parametrize("order", ["ada_first", "local_first"])
def test_route_checks_use_their_own_regime_width(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], order: str
) -> None:
    route = next(
        r.rule for r in load_ruleset("ada_2010") if r.rule.check == "accessible_route_exists"
    ).model_dump(mode="json")
    route.update(
        id="test.local-route",
        code=CODE,
        edition=EDITION,
        jurisdiction=SLUG,
        source_text=None,
        source_url="https://example.test/route",
        exceptions=[],
    )
    write_rules(rules_dir, f"local/{SLUG}", width_rule(), route)
    layers = ["ada_2010", f"local/{SLUG}"]
    if order == "local_first":
        layers.reverse()
    report = run(model, resolve(layers, rules_dir), adoption_records=records)
    assert all(f.verdict is Verdict.UNKNOWN for f in report.for_rule("ada2010.accessible-route"))
    assert all(f.verdict is Verdict.FAIL for f in report.for_rule("test.local-route"))


def test_entrance_only_scope_assumptions_block_comparison(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    report = run(
        model,
        resolved_width(
            rules_dir,
            selection={
                "element": "opening",
                "filter": {"kind": ["door"]},
                "obligated_by": ["ada2010.scoping.entrances"],
            },
        ),
        adoption_records=records,
    )
    assert report.governing_requirements == []
    assert any("scoping" in item.reason for item in report.governing_not_derived)
    assert widths(report)["ada2010.door-clear-width"] is Verdict.PASS


@pytest.mark.parametrize("problem", ["incomplete", "unconfirmed", "different_authority"])
def test_only_confirmed_verified_adoption_chain_can_govern(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord], problem: str
) -> None:
    if problem == "incomplete":
        records = [records[0].model_copy(update={"verified_by": None})]
    elif problem == "unconfirmed":
        model = model.model_copy(
            update={
                "project": model.project.model_copy(
                    update={"jurisdiction_source": "address_proposed"}
                )
            }
        )
    else:
        records = [records[0].model_copy(update={"slug": "other-authority"})]
        model = model.model_copy(
            update={"project": model.project.model_copy(update={"jurisdiction": "other-authority"})}
        )
    report = run(model, resolved_width(rules_dir), adoption_records=records)
    assert report.governing_requirements == []
    if problem == "unconfirmed":
        assert all(f.provisional for f in report.for_rule("test.local-width"))
        assert report.governing_not_derived
    else:
        expected = Verdict.NOT_APPLICABLE if problem == "different_authority" else Verdict.UNKNOWN
        assert all(f.verdict is expected for f in report.for_rule("test.local-width"))


def test_unadopted_base_edition_cannot_govern(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    write_rules(
        rules_dir,
        "ibc_style",
        width_rule("test.base-width", jurisdiction=None, edition="unadopted-test-edition"),
    )
    report = run(model, resolve(["ada_2010", "ibc_style"], rules_dir), adoption_records=records)
    assert report.governing_requirements == []
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in report.for_rule("test.base-width"))


def test_maximum_comparison_chooses_smallest_limit(rules_dir: Path) -> None:
    from plancheck.compliance.governing import cite, derive_governing
    from plancheck.compliance.results import Finding

    resolved = resolved_width(rules_dir)
    loaded = {r.rule.id: r for r in resolved.rules}
    sources = [
        cite(
            Finding(
                rule_id=rule_id,
                code=loaded[rule_id].rule.code,
                section="TEST",
                title="Synthetic maximum contract",
                verdict=Verdict.PASS,
                element_ids=["test-element"],
                required=f"{limit} mm",
                required_mm=limit,
                measured=exact(100),
                semantics=MeasurementSemantics(
                    quantity="synthetic.distance", basis="synthetic.path", relation="max"
                ),
            ),
            loaded[rule_id],
        )
        for rule_id, limit in [("ada2010.door-clear-width", 1200), ("test.local-width", 900)]
    ]
    rows, omitted = derive_governing(sources, loaded)
    assert omitted == []
    assert len(rows) == 1
    assert rows[0].required_mm == 900
    assert rows[0].governing_rule_ids == ["test.local-width"]


def test_compound_turning_requirements_are_not_compared_as_scalar_diameters(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    data = next(
        r.rule for r in load_ruleset("ada_2010") if r.rule.check == "turning_space"
    ).model_dump(mode="json")
    data.update(
        id="test.local-turning",
        code=CODE,
        edition=EDITION,
        jurisdiction=SLUG,
        source_text=None,
        source_url="https://example.test/turning",
    )
    write_rules(rules_dir, f"local/{SLUG}", data)
    model = model.model_copy(
        update={"rooms": [r.model_copy(update={"room_type": "bathroom"}) for r in model.rooms]}
    )
    report = run(model, resolve(["ada_2010", f"local/{SLUG}"], rules_dir), adoption_records=records)
    assert report.governing_requirements == []
    assert len(report.governing_not_derived) == 2
    assert all("semantics unavailable" in item.reason for item in report.governing_not_derived)


def test_amendment_chains_follow_active_parent_and_keep_all_citations(
    model: BuildingModel, rules_dir: Path, records: list[AdoptionRecord]
) -> None:
    base_and_amendment(rules_dir, "replace")
    city = width_rule(
        "test.child-width",
        jurisdiction="test-child",
        amends={"rule": "test.local-width", "mode": "replace"},
        requirement={"min_clear_width": {"value": 1100, "unit": "mm"}},
    )
    write_rules(rules_dir, "local/test-child", city)
    records.append(records[0].model_copy(update={"slug": "test-child", "parent": SLUG}))
    model = model.model_copy(
        update={"project": model.project.model_copy(update={"jurisdiction": "test-child"})}
    )
    resolved = resolve(["ada_2010", "ibc_style", f"local/{SLUG}", "local/test-child"], rules_dir)
    report = run(model, resolved, adoption_records=records)
    assert len(report.amendments) == 2
    assert all(a.status == "applied" for a in report.amendments)
    assert len(report.governing_requirements) == 2
    assert all(g.governing_rule_ids == ["test.child-width"] for g in report.governing_requirements)
    assert report.for_rule("test.base-width") == []
    assert report.for_rule("test.local-width") == []
    # If a child purports to amend an inactive parent, do not invent its fallback.
    model = model.model_copy(
        update={"project": model.project.model_copy(update={"permit_date": date(2023, 1, 1)})}
    )
    report = run(model, resolved, adoption_records=records)
    assert report.amendments[1].status == "unknown"
    assert report.governing_requirements == []
    assert report.governing_not_derived
