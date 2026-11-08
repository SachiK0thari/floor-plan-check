"""Check functions on hand-built geometry with answers worked out on paper."""

from __future__ import annotations

from datetime import date

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon

from plancheck.compliance.checks.accessible_route import accessible_route_exists
from plancheck.compliance.checks.door_maneuvering_clearance import door_maneuvering_clearance
from plancheck.compliance.checks.opening_clear_width import opening_clear_width
from plancheck.compliance.checks.turning_space import largest_circle, t_fits, turning_space
from plancheck.compliance.context import CheckContext
from plancheck.compliance.registry import load_ruleset
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict
from plancheck.model.types import (
    BuildingModel,
    Fixture,
    Measured,
    Point,
    ProjectContext,
    Room,
)
from tests.conftest import exact, wall

IN = 25.4
PROJECT = ProjectContext(
    facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
)


@pytest.fixture(scope="module")
def rules() -> dict[str, Rule]:
    return {loaded.rule.id: loaded.rule for loaded in load_ruleset("ada_2010")}


def ctx(deduction_mm: float | None = 50.0, sigma_mm: float = 0.0, k: float = 2.0) -> CheckContext:
    deductions = {}
    if deduction_mm is not None:
        deductions["swing"] = Measured(value_mm=deduction_mm, sigma_mm=sigma_mm, source="user")
    return CheckContext(k=k, clear_width_deductions=deductions)


def with_clear_width(model: BuildingModel, **widths: float) -> BuildingModel:
    openings = [
        o.model_copy(update={"clear_width": exact(widths[o.id])}) if o.id in widths else o
        for o in model.openings
    ]
    return model.model_copy(update={"openings": openings})


# ---------------------------------------------------------------- clear width


def test_clear_width_from_leaf_and_deduction(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    rule = rules["ada2010.door-clear-width"]
    d1 = two_rooms.opening("D1")  # 36 in leaf
    passing = opening_clear_width(two_rooms, rule, d1, ctx(deduction_mm=50))
    assert passing.verdict is Verdict.PASS
    assert passing.measured is not None
    assert passing.measured.value_mm == pytest.approx(914.4 - 50)
    assert (passing.required, passing.required_mm) == ("32 in", pytest.approx(812.8))

    failing = opening_clear_width(two_rooms, rule, d1, ctx(deduction_mm=110))
    assert failing.verdict is Verdict.FAIL  # 804.4 mm


def test_clear_width_needs_a_deduction_or_a_measurement(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    rule = rules["ada2010.door-clear-width"]
    d1 = two_rooms.opening("D1")
    unknown = opening_clear_width(two_rooms, rule, d1, ctx(deduction_mm=None))
    assert unknown.verdict is Verdict.UNKNOWN
    assert "no deduction configured for 'swing'" in (unknown.reason or "")

    measured = with_clear_width(two_rooms, D1=812.8).opening("D1")
    at_limit = opening_clear_width(two_rooms, rule, measured, ctx(deduction_mm=None))
    assert at_limit.verdict is Verdict.PASS  # exactly 32 in


def test_clear_width_uncertainty_gives_borderline(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    rule = rules["ada2010.door-clear-width"]
    d1 = two_rooms.opening("D1")
    # 914.4 - 95 = 819.4, only 6.6 mm over the limit, with sigma 10: within 2 sigma.
    result = opening_clear_width(two_rooms, rule, d1, ctx(deduction_mm=95, sigma_mm=10))
    assert result.verdict is Verdict.BORDERLINE
    assert result.measured is not None
    assert result.measured.sigma_mm == pytest.approx(10)


def test_deep_opening_needs_the_larger_width(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # A 700 mm thick wall is deeper than 24 in, so 36 in applies and a 34 in clear fails.
    rule = rules["ada2010.door-clear-width"]
    thick = [
        w.model_copy(update={"thickness": exact(700.0)}) if w.id == "W5" else w
        for w in two_rooms.walls
    ]
    model = with_clear_width(two_rooms.model_copy(update={"walls": thick}), D1=34 * IN)
    result = opening_clear_width(model, rule, model.opening("D1"), ctx(deduction_mm=None))
    assert (result.verdict, result.required) == (Verdict.FAIL, "36 in")
    assert "larger minimum applies" in (result.reason or "")


def test_surfaced_exceptions_are_listed(two_rooms: BuildingModel, rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.door-clear-width"]
    result = opening_clear_width(two_rooms, rule, two_rooms.opening("D1"), ctx())
    assert result.surfaced_exceptions == ["alteration-latch-stop"]


# ---------------------------------------------------------------- maneuvering clearance


def fixture_in(room_id: str, x0: float, y0: float, x1: float, y1: float) -> Fixture:
    return Fixture(
        id=f"F-{x0:.0f}-{y0:.0f}",
        kind="casework",
        footprint=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        room_id=room_id,
        provenance="user_edit",
    )


def test_clear_floor_on_both_sides_is_not_proof(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # D1 opens into R1 (pull side) with nothing near it; the check can only prove failure.
    rule = rules["ada2010.door-maneuvering-clearance"]
    result = door_maneuvering_clearance(two_rooms, rule, two_rooms.opening("D1"), ctx())
    assert result.verdict is Verdict.PASS  # before the engine restricts it
    assert result.reason == "front approach assumed; clear of walls and modelled fixtures"
    assert [e.label for e in result.evidence] == ["pull side", "push side"]


def test_casework_in_front_of_the_pull_side_fails(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # A counter 50 mm in front of the door face (x = 3950) on the pull side.
    rule = rules["ada2010.door-maneuvering-clearance"]
    model = two_rooms.model_copy(update={"fixtures": [fixture_in("R1", 3000, 1400, 3900, 3000)]})
    result = door_maneuvering_clearance(model, rule, model.opening("D1"), ctx())
    assert result.verdict is Verdict.FAIL
    assert "pull-side depth 51 mm" in (result.reason or "")  # 50 mm plus the 1 mm skin


def test_obstruction_beyond_the_latch_fails(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # D1's latch is at y = 2482.2; casework starts 117.8 mm beyond it, within the 60 in depth.
    rule = rules["ada2010.door-maneuvering-clearance"]
    model = two_rooms.model_copy(update={"fixtures": [fixture_in("R1", 3500, 2600, 3950, 2800)]})
    result = door_maneuvering_clearance(model, rule, model.opening("D1"), ctx())
    assert result.verdict is Verdict.FAIL
    assert "latch clearance 119 mm" in (result.reason or "")


def test_push_side_has_no_latch_requirement(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # The same casework on the push side (R2), beyond the latch, does not matter.
    rule = rules["ada2010.door-maneuvering-clearance"]
    model = two_rooms.model_copy(update={"fixtures": [fixture_in("R2", 4050, 2600, 4500, 2800)]})
    result = door_maneuvering_clearance(model, rule, model.opening("D1"), ctx())
    assert result.verdict is Verdict.PASS


def test_wall_close_to_the_push_side_fails(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    # A partition 1000 mm from the door face on the push side: less than 48 in.
    rule = rules["ada2010.door-maneuvering-clearance"]
    walls = [*two_rooms.walls, wall("W6", (5050, 100), (5050, 3900), 100.0)]
    model = two_rooms.model_copy(update={"walls": walls})
    result = door_maneuvering_clearance(model, rule, model.opening("D1"), ctx())
    assert result.verdict is Verdict.FAIL
    assert "push-side depth 951 mm" in (result.reason or "")  # 5000 - 4050, plus the 1 mm skin


def test_unknown_swing_gives_unknown(two_rooms: BuildingModel, rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.door-maneuvering-clearance"]
    door = two_rooms.opening("D1").model_copy(update={"hinge_at": None})
    result = door_maneuvering_clearance(two_rooms, rule, door, ctx())
    assert result.verdict is Verdict.UNKNOWN


# ---------------------------------------------------------------- turning space


def room_model(polygon: list[Point], fixtures: list[Fixture] | None = None) -> BuildingModel:
    """A model with one bathroom of the given clear outline; walls are irrelevant here."""
    boundary = Polygon(polygon).buffer(50, join_style="mitre")
    room = Room(
        id="R1",
        boundary=[(x, y) for x, y in list(boundary.exterior.coords)[:-1]],
        clear_polygon=polygon,
        room_type="bathroom",
        provenance="user_edit",
    )
    return BuildingModel(
        walls=[wall("W1", (0, -1000), (1000, -1000), 100.0)],
        rooms=[room],
        fixtures=fixtures or [],
        project=PROJECT,
    )


def box(w: float, d: float) -> list[Point]:
    return [(0, 0), (w, 0), (w, d), (0, d)]


T_ROOM: list[Point] = [
    (325, 0),
    (1275, 0),
    (1275, 700),
    (1600, 700),
    (1600, 1650),
    (0, 1650),
    (0, 700),
    (325, 700),
]  # a 1600 x 950 bar with a 950 x 700 stem: no 60 in circle fits, but a T does


def test_largest_circle_in_a_square() -> None:
    diameter, centre = largest_circle(Polygon(box(1600, 1600)))
    assert diameter == pytest.approx(1600, abs=2)
    assert centre == pytest.approx((800, 800), abs=2)


def test_t_fits_in_its_own_square_and_not_in_a_smaller_one() -> None:
    # The grid only counts cells wholly inside the floor, so it is conservative by up to
    # one cell (10 mm) per side; a 1550 square fits, a 1500 one cannot.
    assert t_fits(Polygon(box(1550, 1550)), 60 * IN, 36 * IN) is not None
    assert t_fits(Polygon(box(1500, 1600)), 60 * IN, 36 * IN) is None


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_t_shaped_room_fits_a_t_in_every_orientation(angle: int) -> None:
    shape = rotate(Polygon(T_ROOM), angle, origin=(0, 0))
    assert t_fits(shape, 60 * IN, 36 * IN) is not None


def test_t_needs_the_full_stem_width() -> None:
    narrow: list[Point] = [
        (350, 0),
        (1250, 0),
        (1250, 700),
        (1600, 700),
        (1600, 1650),
        (0, 1650),
        (0, 700),
        (350, 700),
    ]  # stem 900 wide, less than 36 in
    assert t_fits(Polygon(narrow), 60 * IN, 36 * IN) is None


def test_circle_fits(rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.toilet-room-turning-space"]
    model = room_model(box(1600, 1600))
    result = turning_space(model, rule, model.room("R1"), ctx())
    assert result.verdict is Verdict.PASS
    assert "fits as a circle" in (result.reason or "")
    assert result.measured is not None
    assert result.measured.value_mm == pytest.approx(1600, abs=2)


def test_neither_shape_fits(rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.toilet-room-turning-space"]
    model = room_model(box(1500, 2000))
    result = turning_space(model, rule, model.room("R1"), ctx())
    assert result.verdict is Verdict.FAIL


def test_t_shape_rescues_a_room_with_no_circle(rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.toilet-room-turning-space"]
    model = room_model(T_ROOM)
    result = turning_space(model, rule, model.room("R1"), ctx())
    assert result.verdict is Verdict.PASS
    assert "fits as a T-shape" in (result.reason or "")


def test_modelled_fixtures_take_floor_away(rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.toilet-room-turning-space"]
    counter = fixture_in("R1", 0, 1200, 1600, 1600)  # leaves 1600 x 1200
    model = room_model(box(1600, 1600), [counter])
    result = turning_space(model, rule, model.room("R1"), ctx())
    assert result.verdict is Verdict.FAIL
    assert result.measured is not None
    assert result.measured.value_mm == pytest.approx(1200, abs=2)


def test_turning_space_near_the_limit_is_borderline_with_uncertainty(
    rules: dict[str, Rule],
) -> None:
    rule = rules["ada2010.toilet-room-turning-space"]
    model = room_model(box(1530, 1530))  # 6 mm over the 1524 mm circle
    uncertain = model.model_copy(
        update={
            "walls": [
                wall("W1", (0, -1000), (1000, -1000), 100.0).model_copy(
                    update={"thickness": Measured(value_mm=100, sigma_mm=10, source="geometry")}
                )
            ]
        }
    )
    assert turning_space(model, rule, model.room("R1"), ctx()).verdict is Verdict.PASS
    assert turning_space(uncertain, rule, uncertain.room("R1"), ctx()).verdict is Verdict.BORDERLINE


# ---------------------------------------------------------------- accessible route


def route_ctx(model_ctx: CheckContext, rules: dict[str, Rule]) -> CheckContext:
    import dataclasses

    return dataclasses.replace(model_ctx, door_rule=rules["ada2010.door-clear-width"])


def test_route_through_passing_doors(two_rooms: BuildingModel, rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.accessible-route"]
    result = accessible_route_exists(
        two_rooms, rule, two_rooms.room("R1"), route_ctx(ctx(50), rules)
    )
    assert result.verdict is Verdict.PASS
    assert result.reason == "route from the exterior through D2, D1"


def test_route_is_only_as_good_as_its_worst_door(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    rule = rules["ada2010.accessible-route"]
    model = with_clear_width(two_rooms, D2=900.0, D1=812.0)  # D1 fails by 0.8 mm
    c = route_ctx(ctx(None), rules)
    assert accessible_route_exists(model, rule, model.room("R2"), c).verdict is Verdict.PASS
    assert accessible_route_exists(model, rule, model.room("R1"), c).verdict is Verdict.FAIL

    borderline = with_clear_width(two_rooms, D2=900.0).model_copy(
        update={
            "openings": [
                o.model_copy(
                    update={"clear_width": Measured(value_mm=815, sigma_mm=5, source="geometry")}
                )
                if o.id == "D1"
                else o
                for o in with_clear_width(two_rooms, D2=900.0).openings
            ]
        }
    )
    assert (
        accessible_route_exists(borderline, rule, borderline.room("R1"), c).verdict
        is Verdict.BORDERLINE
    )


def test_no_entrance_means_no_route(two_rooms: BuildingModel, rules: dict[str, Rule]) -> None:
    rule = rules["ada2010.accessible-route"]
    model = with_clear_width(two_rooms, D2=700.0, D1=900.0)
    result = accessible_route_exists(model, rule, model.room("R1"), route_ctx(ctx(None), rules))
    assert result.verdict is Verdict.FAIL
    assert result.reason == "no route from the exterior through doors that could comply"


def test_route_without_a_door_rule_is_unknown(
    two_rooms: BuildingModel, rules: dict[str, Rule]
) -> None:
    rule = rules["ada2010.accessible-route"]
    result = accessible_route_exists(two_rooms, rule, two_rooms.room("R1"), ctx())
    assert result.verdict is Verdict.UNKNOWN
