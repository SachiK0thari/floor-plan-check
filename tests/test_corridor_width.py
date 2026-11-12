"""Known-answer corridor profiles, with thresholds read from the verified rule."""

from __future__ import annotations

from datetime import date

import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from plancheck.compliance.checks.corridor_min_width import corridor_min_width
from plancheck.compliance.context import CheckContext
from plancheck.compliance.engine import run
from plancheck.compliance.registry import load_ruleset, resolve
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict
from plancheck.model.types import BuildingModel, Measured, Point, ProjectContext, Room
from tests.conftest import wall


@pytest.fixture
def rule() -> Rule:
    return next(r.rule for r in load_ruleset("ada_2010") if r.rule.check == "corridor_min_width")


def model_for(
    shape: Polygon, paths: list[list[Point]] | None = None, sigma: float = 0
) -> BuildingModel:
    room = Room(
        id="C",
        boundary=list(shape.exterior.coords),
        clear_polygon=list(shape.exterior.coords),
        room_type="corridor",
        corridor_paths=paths or [],
        provenance="user_edit",
    )
    w = wall("W", (-1000, -1000), (-500, -1000), 100).model_copy(
        update={"thickness": Measured(value_mm=100, sigma_mm=sigma, source="geometry")}
    )
    return BuildingModel(
        rooms=[room],
        walls=[w],
        project=ProjectContext(
            facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
        ),
    )


def check(model: BuildingModel, rule: Rule) -> Verdict:
    return corridor_min_width(model, rule, model.rooms[0], CheckContext()).verdict


@pytest.mark.parametrize(
    ("delta", "expected"), [(-1, Verdict.FAIL), (0, Verdict.PASS), (1, Verdict.PASS)]
)
def test_straight_boundary(rule: Rule, delta: float, expected: Verdict) -> None:
    width = rule.requirement["min_clear_width"].mm + delta
    assert check(model_for(box(0, 0, 5000, width)), rule) is expected


def pinches(
    rule: Rule, length: float, gap: float | None = None, reduced_delta: float = 0
) -> BuildingModel:
    p = rule.exceptions[0].params
    width = rule.requirement["min_clear_width"].mm
    reduced = p["reduced_width"].mm + reduced_delta
    pieces = [box(0, 0, 1000, width), box(1000, 0, 1000 + length, reduced)]
    end = 1000 + length
    if gap is not None:
        pieces.extend(
            [box(end, 0, end + gap, width), box(end + gap, 0, end + gap + length, reduced)]
        )
        end += gap + length
    pieces.append(box(end, 0, end + 1000, width))
    shape = unary_union(pieces)
    assert isinstance(shape, Polygon)
    return model_for(shape, [[(0, reduced / 2), (end + 1000, reduced / 2)]])


@pytest.mark.parametrize(
    ("delta", "expected"), [(-1, Verdict.PASS), (0, Verdict.PASS), (1, Verdict.FAIL)]
)
def test_narrow_run_length_boundary(rule: Rule, delta: float, expected: Verdict) -> None:
    assert (
        check(pinches(rule, rule.exceptions[0].params["max_length"].mm + delta), rule) is expected
    )


@pytest.mark.parametrize(
    ("delta", "expected"), [(-1, Verdict.FAIL), (0, Verdict.PASS), (1, Verdict.PASS)]
)
def test_separation_boundary(rule: Rule, delta: float, expected: Verdict) -> None:
    p = rule.exceptions[0].params
    assert check(pinches(rule, 100, p["separation_length"].mm + delta), rule) is expected


def test_submillimetre_pinch_is_not_missed(rule: Rule) -> None:
    model = pinches(rule, 0.01, reduced_delta=-1)
    result = corridor_min_width(model, rule, model.rooms[0], CheckContext())
    assert result.verdict is Verdict.FAIL
    assert result.evidence
    assert result.measured is not None
    assert result.measured.value_mm == pytest.approx(
        rule.exceptions[0].params["reduced_width"].mm - 1
    )
    assert result.surfaced_exceptions == ["turns-and-passing"]


def test_l_and_t_do_not_fail_at_corners(rule: Rule) -> None:
    l_shape = unary_union([box(0, 0, 4000, 1000), box(3000, 0, 4000, 4000)])
    t_shape = unary_union([box(0, 0, 7000, 1000), box(3000, 0, 4000, 4000)])
    assert isinstance(l_shape, Polygon)
    assert isinstance(t_shape, Polygon)
    assert (
        check(model_for(l_shape, [[(0, 500), (4000, 500)], [(3500, 0), (3500, 4000)]]), rule)
        is Verdict.PASS
    )
    paths: list[list[Point]] = [[(0, 500), (7000, 500)], [(3500, 500), (3500, 4000)]]
    assert check(model_for(t_shape, paths), rule) is Verdict.PASS


def test_missing_and_unsupported_paths(rule: Rule) -> None:
    l_shape = unary_union([box(0, 0, 4000, 1000), box(3000, 0, 4000, 4000)])
    assert isinstance(l_shape, Polygon)
    assert check(model_for(l_shape), rule) is Verdict.UNKNOWN
    assert (
        check(model_for(box(0, 0, 5000, 1000), [[(0, 0), (5000, 1000)]]), rule) is Verdict.UNKNOWN
    )
    assert (
        check(model_for(box(0, 0, 5000, 1000), [[(0, 500), (6000, 500)]]), rule) is Verdict.UNKNOWN
    )
    assert check(model_for(box(0, 0, 5000, 1000), [[(0, 500)]]), rule) is Verdict.UNKNOWN


def test_width_and_length_uncertainty(rule: Rule) -> None:
    width = rule.requirement["min_clear_width"].mm
    assert check(model_for(box(0, 0, 5000, width + 1), sigma=2), rule) is Verdict.BORDERLINE
    # Keep reduced width comfortably above its limit to isolate length uncertainty.
    model = pinches(rule, rule.exceptions[0].params["max_length"].mm, reduced_delta=30)
    model = model.model_copy(update={"scale_rel_sigma": 0.001})
    assert check(model, rule) is Verdict.BORDERLINE


@pytest.mark.parametrize("angle", [0, 37, 90, 180])
def test_rotation_translation(rule: Rule, angle: float) -> None:
    model = pinches(rule, 100)
    room = model.rooms[0]
    shape = translate(rotate(Polygon(room.clear_polygon), angle, origin=(0, 0)), 123, -456)
    route = translate(rotate(LineString(room.corridor_paths[0]), angle, origin=(0, 0)), 123, -456)
    assert check(model_for(shape, [list(route.coords)]), rule) is Verdict.PASS


def test_registered_engine_finding(rule: Rule) -> None:
    model = model_for(box(0, 0, 5000, 1000))
    report = run(model, resolve(["ada_2010"]))
    findings = [f for f in report.findings if f.rule_id == rule.id]
    assert len(findings) == 1
    assert findings[0].verdict is Verdict.PASS


@pytest.mark.parametrize(
    ("delta", "expected"), [(-1, Verdict.FAIL), (0, Verdict.PASS), (1, Verdict.PASS)]
)
def test_reduced_width_boundary(rule: Rule, delta: float, expected: Verdict) -> None:
    assert check(pinches(rule, 100, reduced_delta=delta), rule) is expected


def test_incomplete_arm_coverage_is_unknown(rule: Rule) -> None:
    shape = unary_union([box(0, 0, 7000, 1000), box(3000, 0, 4000, 4000)])
    assert isinstance(shape, Polygon)
    assert check(model_for(shape, [[(0, 500), (7000, 500)]]), rule) is Verdict.UNKNOWN


def test_narrow_branch_needs_distance_review(rule: Rule) -> None:
    shape = unary_union([box(0, 0, 7000, 1000), box(3000, 0, 3850, 4000)])
    assert isinstance(shape, Polygon)
    paths: list[list[Point]] = [[(0, 500), (7000, 500)], [(3425, 0), (3425, 4000)]]
    assert check(model_for(shape, paths), rule) is Verdict.UNKNOWN


def test_separation_uncertainty(rule: Rule) -> None:
    p = rule.exceptions[0].params
    model = pinches(rule, 100, p["separation_length"].mm, reduced_delta=30)
    assert check(model.model_copy(update={"scale_rel_sigma": 0.001}), rule) is Verdict.BORDERLINE


def test_fixture_pinch_and_serialization(rule: Rule) -> None:
    from plancheck.model.types import Fixture

    model = model_for(box(0, 0, 5000, 1000), [[(0, 400), (5000, 400)]])
    fixture = Fixture(
        id="F",
        kind="casework",
        room_id="C",
        provenance="user_edit",
        footprint=[(2000, 700), (2000.01, 700), (2000.01, 1000), (2000, 1000)],
    )
    model = model.model_copy(update={"fixtures": [fixture]})
    restored = BuildingModel.model_validate_json(model.model_dump_json())
    assert restored.rooms[0].corridor_paths == model.rooms[0].corridor_paths
    assert check(restored, rule) is Verdict.FAIL


def test_mirror(rule: Rule) -> None:
    from shapely.affinity import scale

    model = pinches(rule, 100)
    room = model.rooms[0]
    shape = scale(Polygon(room.clear_polygon), xfact=-1, yfact=1, origin=(0, 0))
    route = scale(LineString(room.corridor_paths[0]), xfact=-1, yfact=1, origin=(0, 0))
    assert check(model_for(shape, [list(route.coords)]), rule) is Verdict.PASS


def test_cross_corridor_path_cannot_hide_narrow_width(rule: Rule) -> None:
    assert (
        check(model_for(box(0, 0, 5000, 700), [[(2500, 0), (2500, 700)]]), rule) is Verdict.UNKNOWN
    )
