from __future__ import annotations

import math
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plancheck.compliance.verdict import (
    Verdict,
    all_of,
    any_of,
    at_least,
    decide_max,
    decide_min,
    guard_factor,
    margin_in_sigmas,
    restrict,
    same_or_borderline,
)
from plancheck.model.types import Measured

P, F, B, U, NA = (
    Verdict.PASS,
    Verdict.FAIL,
    Verdict.BORDERLINE,
    Verdict.UNKNOWN,
    Verdict.NOT_APPLICABLE,
)
LIMIT = 32 * 25.4  # 812.8 mm


def m(value: float, sigma: float = 0.0) -> Measured:
    return Measured(value_mm=value, sigma_mm=sigma, source="geometry")


def test_guard_factor_comes_from_config() -> None:
    assert guard_factor() == 2.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [(LIMIT - 1, F), (LIMIT, P), (LIMIT + 1, P)],
)
def test_exact_measurements_at_the_boundary(value: float, expected: Verdict) -> None:
    assert decide_min(m(value), LIMIT, k=2) is expected


def test_value_computed_in_inches_passes_at_the_limit() -> None:
    # 0.1 + 0.2 style rounding must not turn "exactly 32 in" into a fail.
    assert decide_min(m(3.2 * 10 * 25.4), LIMIT, k=2) is P
    assert decide_max(m(3.2 * 10 * 25.4), LIMIT, k=2) is P


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (LIMIT + 21, P),  # clears the limit by more than 2 sigma
        (LIMIT + 20, P),  # exactly 2 sigma clear
        (LIMIT + 19, B),
        (LIMIT - 19, B),
        (LIMIT - 20, B),  # value + 2 sigma equals the limit: not a proven fail
        (LIMIT - 21, F),
    ],
)
def test_guard_band_for_a_minimum(value: float, expected: Verdict) -> None:
    assert decide_min(m(value, sigma=10), LIMIT, k=2) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(979, P), (980, P), (981, B), (1019, B), (1020, B), (1021, F)],
)
def test_guard_band_for_a_maximum(value: float, expected: Verdict) -> None:
    assert decide_max(m(value, sigma=10), 1000, k=2) is expected


def test_k_zero_removes_the_review_band() -> None:
    assert decide_min(m(LIMIT + 1, sigma=50), LIMIT, k=0) is P
    assert decide_min(m(LIMIT - 1, sigma=50), LIMIT, k=0) is F


@given(
    value=st.floats(0, 3000),
    sigma=st.floats(0, 200),
    more=st.floats(0, 200),
    limit=st.floats(100, 2000),
)
def test_more_uncertainty_never_makes_a_verdict_more_definite(
    value: float, sigma: float, more: float, limit: float
) -> None:
    before = decide_min(m(value, sigma), limit, k=2)
    after = decide_min(m(value, sigma + more), limit, k=2)
    assert after in (before, B)


@given(value=st.floats(0, 3000), wider=st.floats(0, 500), sigma=st.floats(0, 100))
def test_a_larger_value_never_turns_a_pass_into_a_fail(
    value: float, wider: float, sigma: float
) -> None:
    order = {F: 0, B: 1, P: 2}
    before = decide_min(m(value, sigma), LIMIT, k=2)
    after = decide_min(m(value + wider, sigma), LIMIT, k=2)
    assert order[after] >= order[before]


def test_restrict() -> None:
    assert restrict(P, "fail_only") is U  # a necessary condition met proves nothing
    assert restrict(F, "fail_only") is F
    assert restrict(B, "fail_only") is B
    assert restrict(F, "pass_only") is U
    assert restrict(P, "pass_only") is P
    assert [restrict(v, "both") for v in (P, F, B, U, NA)] == [P, F, B, U, NA]


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([P, P, P], P),
        ([P, F, P], F),  # one failing door breaks the route
        ([P, B, P], B),
        ([P, U, B], U),  # unknown is weaker than borderline
        ([F, U], F),  # already broken, whatever the unknown turns out to be
        ([P, NA], P),
        ([NA, NA], NA),
        ([], NA),
    ],
)
def test_all_of(members: list[Verdict], expected: Verdict) -> None:
    assert all_of(members) is expected


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([F, P], P),  # one compliant door is enough
        ([F, F], F),
        ([F, B], B),
        ([F, U, B], U),
        ([P, U], P),
        ([NA, F], F),
        ([], F),  # a room with no door has no compliant door
    ],
)
def test_any_of(members: list[Verdict], expected: Verdict) -> None:
    assert any_of(members) is expected


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([P, P], P),
        ([F, F], F),
        ([P, F], B),  # the uncertain input decides between them
        ([P], P),
        ([B, B], B),
    ],
)
def test_same_or_borderline(members: list[Verdict], expected: Verdict) -> None:
    assert same_or_borderline(*members) is expected


def test_same_or_borderline_needs_a_verdict() -> None:
    with pytest.raises(ValueError, match="at least one"):
        same_or_borderline()


@pytest.mark.parametrize(
    ("count", "members", "expected"),
    [
        (2, [P, P, F], P),
        (2, [P, F, F], F),
        (2, [P, B, F], B),
        (2, [P, U, F], U),
        (3, [P, P, B, F], B),
        (3, [P, B, F, F], F),
    ],
)
def test_at_least(count: int, members: list[Verdict], expected: Verdict) -> None:
    assert at_least(count, members) is expected


@pytest.mark.parametrize(
    ("count", "members", "expected"),
    [
        (1, [Verdict.NOT_APPLICABLE], Verdict.NOT_APPLICABLE),
        (1, [Verdict.NOT_APPLICABLE, Verdict.UNKNOWN], Verdict.UNKNOWN),
        (1, [Verdict.NOT_APPLICABLE, Verdict.PASS], Verdict.PASS),
        (1, [], Verdict.FAIL),
        (0, [], Verdict.PASS),
    ],
)
def test_scoped_group_cardinality(count: int, members: list[Verdict], expected: Verdict) -> None:
    from plancheck.compliance.verdict import scoped_at_least

    assert scoped_at_least(count, members) is expected


@pytest.mark.parametrize(
    ("value", "sigma", "limit", "relation", "expected"),
    [
        (830.0, 5.0, 812.8, "min", 3.44),
        (800.0, 5.0, 812.8, "min", -2.56),
        (600.0, 20.0, 609.6, "max", 0.48),
        (812.8, 5.0, 812.8, "min", 0.0),
        (900.0, 0.0, 812.8, "min", math.inf),
        (700.0, 0.0, 812.8, "min", -math.inf),
        (812.8, 0.0, 812.8, "min", 0.0),
    ],
)
def test_margin_in_sigmas(
    value: float, sigma: float, limit: float, relation: Any, expected: float
) -> None:
    m = Measured(value_mm=value, sigma_mm=sigma, source="user")
    assert margin_in_sigmas(m, limit, relation) == pytest.approx(expected)
    # Consistent with the decision rule at k = 2.
    verdict = (decide_min if relation == "min" else decide_max)(m, limit, 2.0)
    margin = margin_in_sigmas(m, limit, relation)
    assert (verdict is P) == (margin >= 2 or (margin == 0.0 and sigma == 0))
