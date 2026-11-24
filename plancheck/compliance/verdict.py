"""The single decision rule (docs/PROJECT_SPEC.md §9.3).

Checks return measurements. Only this module turns a measurement into a verdict, and only
this module combines verdicts.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from enum import StrEnum
from functools import cache
from typing import Literal

from plancheck.config import load_config
from plancheck.model.types import Measured

_EPS_MM = 1e-6
"""Absorbs float rounding, so a value exactly at the limit (32 in = 812.8 mm) passes."""


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BORDERLINE = "borderline"  # the uncertainty interval straddles the limit
    UNKNOWN = "unknown"  # an input is missing
    NOT_APPLICABLE = "not_applicable"


@cache
def guard_factor() -> float:
    """``k`` from ``configs/verdict.yaml``."""
    k = float(load_config("verdict")["guard_factor_k"])
    if k < 0:
        raise ValueError("guard_factor_k must not be negative")
    return k


def decide_min(measured: Measured, limit_mm: float, k: float | None = None) -> Verdict:
    """Verdict for a requirement of the form "at least ``limit_mm``".

    Pass only if the value clears the limit by ``k`` standard uncertainties; fail only if
    it falls short by as much; otherwise borderline.
    """
    k = guard_factor() if k is None else k
    band = k * measured.sigma_mm
    if measured.value_mm - band >= limit_mm - _EPS_MM:
        return Verdict.PASS
    if measured.value_mm + band < limit_mm - _EPS_MM:
        return Verdict.FAIL
    return Verdict.BORDERLINE


def decide_max(measured: Measured, limit_mm: float, k: float | None = None) -> Verdict:
    """Verdict for a requirement of the form "at most ``limit_mm``"."""
    k = guard_factor() if k is None else k
    band = k * measured.sigma_mm
    if measured.value_mm + band <= limit_mm + _EPS_MM:
        return Verdict.PASS
    if measured.value_mm - band > limit_mm + _EPS_MM:
        return Verdict.FAIL
    return Verdict.BORDERLINE


def margin_in_sigmas(measured: Measured, limit_mm: float, relation: Literal["min", "max"]) -> float:
    """How far the value clears its limit, in standard uncertainties; negative means short.

    With no uncertainty the margin is infinite in the direction of the result, or zero at
    the limit. ``decide_min`` and ``decide_max`` pass above ``k`` and fail below ``-k``.
    """
    margin = measured.value_mm - limit_mm if relation == "min" else limit_mm - measured.value_mm
    if abs(margin) <= _EPS_MM:
        return 0.0
    if measured.sigma_mm == 0:
        return math.copysign(math.inf, margin)
    return margin / measured.sigma_mm


def restrict(verdict: Verdict, proves: Literal["both", "fail_only", "pass_only"]) -> Verdict:
    """Limit a verdict to what the check can prove.

    A ``fail_only`` check is a necessary condition: meeting it does not prove
    compliance, so a pass becomes unknown. ``pass_only`` is the mirror image.
    """
    if proves == "fail_only" and verdict is Verdict.PASS:
        return Verdict.UNKNOWN
    if proves == "pass_only" and verdict is Verdict.FAIL:
        return Verdict.UNKNOWN
    return verdict


def same_or_borderline(*verdicts: Verdict) -> Verdict:
    """The common verdict when every case agrees, otherwise borderline.

    Used when an input decides which of several limits applies and that input is itself
    uncertain: the result is definite only if every possible limit gives the same answer.
    """
    if not verdicts:
        raise ValueError("same_or_borderline needs at least one verdict")
    first = verdicts[0]
    return first if all(v is first for v in verdicts) else Verdict.BORDERLINE


def at_least(count: int, verdicts: Iterable[Verdict]) -> Verdict:
    """Verdict for "at least ``count`` of these must pass".

    Members that are not applicable are left out. The result is a pass once enough
    members pass, a fail once too few could still pass, and otherwise the weaker of
    unknown and borderline.
    """
    members = [v for v in verdicts if v is not Verdict.NOT_APPLICABLE]
    passed = sum(v is Verdict.PASS for v in members)
    undecided = [v for v in members if v in (Verdict.BORDERLINE, Verdict.UNKNOWN)]
    if passed >= count:
        return Verdict.PASS
    if passed + len(undecided) < count:
        return Verdict.FAIL
    return Verdict.UNKNOWN if Verdict.UNKNOWN in undecided else Verdict.BORDERLINE


def all_of(verdicts: Iterable[Verdict]) -> Verdict:
    """Every member must pass (a route through several doors).

    With no applicable members the result is not applicable.
    """
    members = [v for v in verdicts if v is not Verdict.NOT_APPLICABLE]
    if not members:
        return Verdict.NOT_APPLICABLE
    return at_least(len(members), members)


def scoped_at_least(count: int, verdicts: Iterable[Verdict]) -> Verdict:
    """An obligated group excluded entirely by technical selection is not applicable.

    An actually empty obligation retains its cardinality: needing one door with no
    doors fails, while needing zero passes. Unknown members remain unresolved.
    """
    members = list(verdicts)
    if members and all(v is Verdict.NOT_APPLICABLE for v in members):
        return Verdict.NOT_APPLICABLE
    return at_least(count, members)


def any_of(verdicts: Iterable[Verdict]) -> Verdict:
    """At least one member must pass (one compliant door per room)."""
    return at_least(1, verdicts)
