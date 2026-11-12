from __future__ import annotations

from datetime import date

import pytest

from plancheck.compliance.context import CheckContext
from plancheck.compliance.engine import applicability, run
from plancheck.compliance.registry import ResolvedRules, load_ruleset, resolve
from plancheck.compliance.scoping.doors import doors_serving_rooms, entrance_doors
from plancheck.compliance.verdict import Verdict
from plancheck.model.types import EXTERIOR, BuildingModel, GraphEdge, Measured, ProjectContext
from plancheck.synthetic.generator import generate_model
from tests.conftest import exact

COMMERCIAL = ProjectContext(
    facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
)


@pytest.fixture(scope="module")
def ada() -> ResolvedRules:
    return resolve(["ada_2010"])


def ctx(deduction_mm: float = 50.0) -> CheckContext:
    return CheckContext(
        k=2.0,
        clear_width_deductions={
            "swing": Measured(value_mm=deduction_mm, sigma_mm=0, source="user")
        },
    )


def commercial(model: BuildingModel, **project: object) -> BuildingModel:
    return model.model_copy(update={"project": COMMERCIAL.model_copy(update=project)})


# ---------------------------------------------------------------- applicability


def test_missing_facility_type_is_unknown_not_a_default(ada: ResolvedRules) -> None:
    rule = ada.get("ada2010.door-clear-width").rule
    result = applicability(rule, ProjectContext(work_type="new"))
    assert result.status is Verdict.UNKNOWN
    assert result.reason == "project input missing: ['facility_type', 'permit_date']"


def test_private_house_is_not_covered_by_the_ada(ada: ResolvedRules) -> None:
    rule = ada.get("ada2010.door-clear-width").rule
    result = applicability(
        rule, COMMERCIAL.model_copy(update={"facility_type": "private_residence"})
    )
    assert result.status is Verdict.NOT_APPLICABLE
    assert "private_residence" in (result.reason or "")


def test_project_before_the_compliance_date(ada: ResolvedRules) -> None:
    rule = ada.get("ada2010.door-clear-width").rule
    early = COMMERCIAL.model_copy(update={"permit_date": date(2011, 6, 1)})
    assert applicability(rule, early).status is Verdict.NOT_APPLICABLE
    on_the_day = COMMERCIAL.model_copy(update={"permit_date": date(2012, 3, 15)})
    assert applicability(rule, on_the_day).status is Verdict.PASS


def test_no_permit_date_is_unresolved_even_with_today(ada: ResolvedRules) -> None:
    rule = ada.get("ada2010.door-clear-width").rule
    undated = COMMERCIAL.model_copy(update={"permit_date": None})
    assert applicability(rule, undated, today=date(2011, 1, 1)).status is Verdict.UNKNOWN
    assert applicability(rule, undated, today=date(2026, 1, 1)).status is Verdict.UNKNOWN


# ---------------------------------------------------------------- scoping


def test_doors_serving_rooms(two_rooms: BuildingModel) -> None:
    rule = next(
        r.rule for r in load_ruleset("ada_2010") if r.rule.id == "ada2010.scoping.room-doors"
    )
    groups = {o.group_id: o for o in doors_serving_rooms(two_rooms, rule)}
    assert groups["room:R1"].element_ids == ["D1"]
    assert groups["room:R2"].element_ids == ["D1", "D2"]
    assert all(o.min_count == 1 for o in groups.values())


def test_entrance_share_rounds_up(two_rooms: BuildingModel) -> None:
    rule = next(
        r.rule for r in load_ruleset("ada_2010") if r.rule.id == "ada2010.scoping.entrances"
    )
    (group,) = entrance_doors(two_rooms, rule)
    assert (group.element_ids, group.min_count) == (["D2"], 1)
    # Three entrances at 60 percent: 1.8, so two must comply.
    (group,) = entrance_doors(three_entrances(two_rooms), rule)
    assert (group.element_ids, group.min_count) == (["D2", "D3", "D4"], 2)


def three_entrances(model: BuildingModel) -> BuildingModel:
    """The two-room plan with two more exterior doors: one into R1, one into R2."""
    d2 = model.opening("D2")
    extra = [
        d2.model_copy(update={"id": "D3", "wall_id": "W1", "position_along_wall_mm": 2000.0}),
        d2.model_copy(update={"id": "D4", "wall_id": "W3", "position_along_wall_mm": 2000.0}),
    ]
    graph = model.graph.model_copy(
        update={
            "edges": [
                *model.graph.edges,
                GraphEdge(opening_id="D3", a="R1", b=EXTERIOR),
                GraphEdge(opening_id="D4", a="R2", b=EXTERIOR),
            ]
        }
    )
    return model.model_copy(update={"openings": [*model.openings, *extra], "graph": graph})


# ---------------------------------------------------------------- a full run


def test_run_on_the_two_room_plan(two_rooms: BuildingModel, ada: ResolvedRules) -> None:
    report = run(commercial(two_rooms), ada, ctx(deduction_mm=50))

    widths = {f.element_ids[0]: f for f in report.for_rule("ada2010.door-clear-width")}
    assert {d: f.verdict for d, f in widths.items()} == {
        "D1": Verdict.PASS,
        "D2": Verdict.PASS,
        "WIN1": Verdict.NOT_APPLICABLE,
    }
    assert widths["D1"].obligations == [
        "at least one door serving R1 must comply (206.5.2)",
        "at least one door serving R2 must comply (206.5.2)",
    ]
    assert any(o.startswith("at least 60% of entrances (1 of 1)") for o in widths["D2"].obligations)

    # Clear floor around the doors can only be disproved, so the engine says unknown.
    for finding in report.for_rule("ada2010.door-maneuvering-clearance"):
        if finding.verdict is Verdict.NOT_APPLICABLE:
            continue
        assert finding.verdict is Verdict.UNKNOWN
        assert finding.reason is not None
        assert finding.reason.startswith("check can only prove fail only")

    routes = {f.element_ids[0]: f.verdict for f in report.for_rule("ada2010.accessible-route")}
    assert routes == {"R1": Verdict.UNKNOWN, "R2": Verdict.UNKNOWN}  # a route on plan is not proof

    groups = {(g.rule_id, g.group): g.verdict for g in report.group_findings}
    assert groups[("ada2010.door-clear-width", "room:R1")] is Verdict.PASS
    assert groups[("ada2010.door-clear-width", "entrances")] is Verdict.PASS
    assert groups[("ada2010.door-maneuvering-clearance", "room:R2")] is Verdict.UNKNOWN

    assert report.coverage["not_implemented"] == []
    assert report.coverage["checked"]["ada2010.toilet-room-turning-space"] == {}  # no bathroom
    assert "thresholds" in report.coverage["not_visible_on_a_plan"]
    assert report.fingerprint == ada.fingerprint()


def test_one_narrow_door_fails_its_room_but_not_a_room_with_another(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    # D1 (the only door into R1) at 30 in clear; D2 wide.
    openings = [
        o.model_copy(update={"clear_width": exact(30 * 25.4 if o.id == "D1" else 900.0)})
        for o in two_rooms.openings
    ]
    model = commercial(two_rooms.model_copy(update={"openings": openings}))
    report = run(model, ada, ctx())
    groups = {(g.rule_id, g.group): g.verdict for g in report.group_findings}
    assert groups[("ada2010.door-clear-width", "room:R1")] is Verdict.FAIL
    assert groups[("ada2010.door-clear-width", "room:R2")] is Verdict.PASS  # D2 serves it
    routes = {f.element_ids[0]: f.verdict for f in report.for_rule("ada2010.accessible-route")}
    assert routes["R1"] is Verdict.FAIL
    assert routes["R2"] is Verdict.UNKNOWN


def test_project_without_inputs_produces_unknown_findings(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(two_rooms, ada, ctx())
    assert len(report.findings) == 7
    assert all(f.verdict is Verdict.UNKNOWN for f in report.findings)
    # All seven implemented rules are gated on project inputs.
    assert len(report.coverage["unknown_applicability"]) == 7
    assert report.coverage["not_implemented"] == []
    assert all("facility_type" in reason for _, reason in report.coverage["unknown_applicability"])


def test_house_gets_not_applicable_with_reasons(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms, facility_type="private_residence"), ada, ctx())
    assert len(report.findings) == 7
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in report.findings)
    assert len(report.coverage["not_applicable"]) == 7


def test_unfilled_rule_values_stop_a_rule_from_running(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    rule = ada.get("ada2010.door-clear-width")
    blank = rule.rule.model_copy(
        update={
            "requirement": {
                "min_clear_width": rule.rule.requirement["min_clear_width"].model_copy(
                    update={"value": None}
                )
            },
            "status": "draft",
        }
    )
    resolved = ResolvedRules(
        rulesets=["ada_2010"],
        rules=[
            r if r is not rule else rule.__class__(blank, r.ruleset, r.path, r.sha256)
            for r in ada.rules
        ],
    )
    resolved.not_runnable.append((blank.id, "values not filled in: ['min_clear_width']"))
    report = run(commercial(two_rooms), resolved, ctx())
    assert report.for_rule("ada2010.door-clear-width")[0].verdict is Verdict.UNKNOWN
    assert "not runnable" in (report.for_rule("ada2010.door-clear-width")[0].reason or "")
    assert report.coverage["not_runnable"] == [
        ("ada2010.door-clear-width", "values not filled in: ['min_clear_width']")
    ]


@pytest.mark.parametrize("seed", range(10))
def test_runs_on_generated_plans_without_error(seed: int, ada: ResolvedRules) -> None:
    report = run(commercial(generate_model(seed)), ada, ctx())
    assert report.findings
    assert all(f.verdict is not Verdict.PASS for f in report.for_rule("ada2010.accessible-route"))


# ----------------------------------------------------- unresolved/excluded results


def test_undated_rules_do_not_require_permit_date(ada: ResolvedRules) -> None:
    rule = ada.get("ada2010.door-clear-width").rule.model_copy(
        update={"effective_date": None, "superseded_date": None}
    )
    assert (
        applicability(rule, COMMERCIAL.model_copy(update={"permit_date": None})).status
        is Verdict.PASS
    )


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (date(2025, 12, 31), Verdict.PASS),
        (date(2026, 1, 1), Verdict.NOT_APPLICABLE),
        (None, Verdict.UNKNOWN),
    ],
)
def test_superseded_date_boundary(ada: ResolvedRules, when: date | None, expected: Verdict) -> None:
    rule = ada.get("ada2010.door-clear-width").rule.model_copy(
        update={"effective_date": None, "superseded_date": date(2026, 1, 1)}
    )
    assert (
        applicability(rule, COMMERCIAL.model_copy(update={"permit_date": when})).status is expected
    )


def test_missing_date_is_visible_without_running_checks(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms, permit_date=None), ada, ctx(), today=date(2026, 1, 1))
    assert len(report.findings) == 7
    assert all(
        f.verdict is Verdict.UNKNOWN and "permit_date" in (f.reason or "") for f in report.findings
    )
    assert len(report.coverage["unknown_applicability"]) == 7
    assert len(report.coverage["unresolved"]) == 7
    assert report.coverage["checked"] == {}
    assert report.coverage["excluded"] == []
    assert not any("today" in note for note in report.coverage["notes"])


def test_confirmed_project_exclusion_wins_over_missing_date(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms, facility_type="private_residence", permit_date=None), ada)
    assert len(report.coverage["excluded"]) == 7
    assert report.coverage["unresolved"] == []
    assert all(
        f.verdict is Verdict.NOT_APPLICABLE and "facility_type" in (f.reason or "")
        for f in report.findings
    )


def entrance_scoped_width(ada: ResolvedRules) -> ResolvedRules:
    from dataclasses import replace

    width = ada.get("ada2010.door-clear-width")
    assert width.rule.selection is not None
    selection = width.rule.selection.model_copy(
        update={"obligated_by": ["ada2010.scoping.entrances"]}
    )
    return ResolvedRules(
        rulesets=["ada_2010"],
        rules=[
            ada.get("ada2010.scoping.entrances"),
            replace(width, rule=width.rule.model_copy(update={"selection": selection})),
        ],
    )


def test_resolved_scoping_excludes_interior_door_with_reason(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms), entrance_scoped_width(ada), ctx())
    widths = {f.element_ids[0]: f for f in report.for_rule("ada2010.door-clear-width")}
    assert widths["D1"].verdict is Verdict.NOT_APPLICABLE
    assert "resolved scoping" in (widths["D1"].reason or "")
    assert "ada2010.scoping.entrances" in (widths["D1"].reason or "")
    assert widths["D2"].verdict is Verdict.PASS
    assert widths["WIN1"].verdict is Verdict.NOT_APPLICABLE
    assert report.coverage["checked"]["ada2010.door-clear-width"] == {"pass": 1}
    assert any(f["element_ids"] == ["D1"] for f in report.coverage["excluded"])


@pytest.mark.parametrize(
    "unavailable", ["missing", "not_runnable", "unimplemented", "applicability"]
)
def test_unresolved_scope_is_not_an_exclusion(
    two_rooms: BuildingModel, ada: ResolvedRules, unavailable: str
) -> None:
    from dataclasses import replace

    resolved = entrance_scoped_width(ada)
    scope = resolved.rules[0]
    if unavailable == "missing":
        resolved.rules = resolved.rules[1:]
    elif unavailable == "not_runnable":
        resolved.not_runnable = [(scope.rule.id, "author value missing")]
    elif unavailable == "unimplemented":
        resolved.rules[0] = replace(
            scope, rule=scope.rule.model_copy(update={"check": "future_scope"})
        )
    else:
        applicability_filter = scope.rule.applicability.model_copy(update={"occupancy": ["test"]})
        resolved.rules[0] = replace(
            scope, rule=scope.rule.model_copy(update={"applicability": applicability_filter})
        )
    report = run(commercial(two_rooms), resolved, ctx())
    findings = [f for f in report.for_rule("ada2010.door-clear-width") if f.element_ids != ["WIN1"]]
    assert len(findings) == 2
    assert all(
        f.verdict is Verdict.UNKNOWN and "scoping unresolved" in (f.reason or "") for f in findings
    )
    assert report.coverage["checked"]["ada2010.door-clear-width"] == {}
    assert all(f["element_ids"] not in (["D1"], ["D2"]) for f in report.coverage["excluded"])


def test_missing_selection_attribute_is_unknown(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    model = commercial(two_rooms).model_copy(
        update={
            "openings": [
                o.model_copy(update={"operation": None}) if o.id == "D1" else o
                for o in two_rooms.openings
            ],
            "rooms": [
                r.model_copy(update={"room_type": None}) if r.id == "R1" else r
                for r in two_rooms.rooms
            ],
        }
    )
    report = run(model, ada, ctx())
    maneuver = next(
        f for f in report.for_rule("ada2010.door-maneuvering-clearance") if f.element_ids == ["D1"]
    )
    assert maneuver.verdict is Verdict.UNKNOWN
    assert "operation" in (maneuver.reason or "")
    corridor = next(
        f for f in report.for_rule("ada2010.walking-surface-clear-width") if f.element_ids == ["R1"]
    )
    assert corridor.verdict is Verdict.UNKNOWN
    assert "room_type" in (corridor.reason or "")
    assert any(f["reason"] == maneuver.reason for f in report.coverage["unresolved"])


def test_missing_connectivity_does_not_exempt_or_fail_doors(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    model = commercial(two_rooms).model_copy(
        update={
            "graph": two_rooms.graph.model_copy(
                update={"edges": [e for e in two_rooms.graph.edges if e.opening_id != "D1"]}
            )
        }
    )
    report = run(model, ada, ctx())
    findings = [f for f in report.for_element("D1") if f.rule_id == "ada2010.door-clear-width"]
    assert len(findings) == 1
    assert findings[0].verdict is Verdict.UNKNOWN
    assert "connectivity missing" in (findings[0].reason or "")
    assert all(f.verdict is Verdict.UNKNOWN for f in report.for_rule("ada2010.accessible-route"))


def test_missing_measurement_and_exceptions_remain_visible(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms), ada, CheckContext(clear_width_deductions={}))
    width = next(f for f in report.for_rule("ada2010.door-clear-width") if f.element_ids == ["D2"])
    assert width.verdict is Verdict.UNKNOWN
    assert "no deduction" in (width.reason or "")
    assert "alteration-latch-stop" in width.surfaced_exceptions
    assert "not-a-public-entrance" in width.surfaced_exceptions
    assert any(
        f["rule_id"] == width.rule_id and f["element_ids"] == ["D2"] and f["reason"] == width.reason
        for f in report.coverage["unresolved"]
    )
    assert any(
        f["rule_id"] == width.rule_id and "not-a-public-entrance" in f["exceptions"]
        for f in report.coverage["surfaced_exceptions"]
    )
    entrance_group = next(
        f for f in report.group_findings if f.rule_id == width.rule_id and f.group == "entrances"
    )
    assert "not-a-public-entrance" in entrance_group.surfaced_exceptions


def test_exceptions_survive_pass_fail_and_serialization(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    from plancheck.compliance.engine import Report

    for clear in (700, 900):
        model = commercial(two_rooms).model_copy(
            update={
                "openings": [
                    o.model_copy(update={"clear_width": exact(clear)}) if o.kind == "door" else o
                    for o in two_rooms.openings
                ]
            }
        )
        report = Report.model_validate_json(run(model, ada, ctx()).model_dump_json())
        width = next(
            f for f in report.for_rule("ada2010.door-clear-width") if f.element_ids == ["D2"]
        )
        assert width.verdict is (Verdict.FAIL if clear == 700 else Verdict.PASS)
        assert "not-a-public-entrance" in width.surfaced_exceptions
        assert report.coverage["surfaced_exceptions"]


def test_inapplicable_scope_explains_excluded_elements(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    from dataclasses import replace

    resolved = entrance_scoped_width(ada)
    scope = resolved.rules[0]
    a = scope.rule.applicability.model_copy(update={"work_type": ["alteration"]})
    resolved.rules[0] = replace(scope, rule=scope.rule.model_copy(update={"applicability": a}))
    report = run(commercial(two_rooms), resolved, ctx())
    findings = report.for_rule("ada2010.door-clear-width")
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in findings)
    door = next(f for f in findings if f.element_ids == ["D2"])
    assert "work_type" in (door.reason or "")
    assert report.coverage["checked"]["ada2010.door-clear-width"] == {}
    assert report.coverage["unresolved"] == []


def test_known_selection_exclusion_wins_over_missing_attribute(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    report = run(commercial(two_rooms), ada, ctx())
    window = next(
        f
        for f in report.for_rule("ada2010.door-maneuvering-clearance")
        if f.element_ids == ["WIN1"]
    )
    assert window.verdict is Verdict.NOT_APPLICABLE
    assert "kind" in (window.reason or "")
    assert "operation" not in (window.reason or "")


def test_group_with_only_excluded_members_is_not_applicable(
    two_rooms: BuildingModel, ada: ResolvedRules
) -> None:
    model = commercial(two_rooms).model_copy(
        update={
            "openings": [
                o.model_copy(update={"operation": "sliding"}) if o.kind == "door" else o
                for o in two_rooms.openings
            ]
        }
    )
    report = run(model, ada, ctx())
    groups = [f for f in report.group_findings if f.rule_id == "ada2010.door-maneuvering-clearance"]
    assert groups
    assert all(f.verdict is Verdict.NOT_APPLICABLE for f in groups)
