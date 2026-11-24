"""Technical checks, one module per check type (spec §9.6).

Every check has the same shape: ``check(model, rule, element, ctx) -> CheckOutcome``. A
check measures; it never decides on its own. The only place a measurement becomes a
verdict is ``plancheck.compliance.verdict``.

``CHECKS`` declares each check's contract (review items A1 and A6): the element it tests,
the most it can prove, and the parameter names it reads. The registry rejects rule files
that do not match.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plancheck.compliance.checks.accessible_route import accessible_route_exists
from plancheck.compliance.checks.corridor_min_width import corridor_min_width
from plancheck.compliance.checks.door_maneuvering_clearance import door_maneuvering_clearance
from plancheck.compliance.checks.opening_clear_width import opening_clear_width
from plancheck.compliance.checks.turning_space import turning_space
from plancheck.compliance.contracts import CheckSpec, turning_space_problems

CHECKS: dict[str, CheckSpec] = {
    "opening_clear_width": CheckSpec(
        function=opening_clear_width,
        element="opening",
        proves="both",
        requirement={"min_clear_width": "length"},
        checked_exceptions={
            "deep-opening": {"depth": "length", "min_clear_width": "length"},
            "double-leaf": {},
        },
    ),
    "door_maneuvering_clearance": CheckSpec(
        function=door_maneuvering_clearance,
        element="opening",
        proves="fail_only",
        requirement={
            "pull_perpendicular": "length",
            "pull_beyond_latch": "length",
            "push_perpendicular": "length",
            "push_beyond_latch": "length",
        },
    ),
    "turning_space": CheckSpec(
        function=turning_space,
        element="room",
        proves="fail_only",
        requirement={
            "circle_diameter": "length",
            "t_square": "length",
            "t_width": "length",
            "t_arm_clear": "length",
            "t_base_clear": "length",
        },
        checked_exceptions={"door-swing": {}},
        rule_problems=turning_space_problems,
    ),
    "corridor_min_width": CheckSpec(
        function=corridor_min_width,
        element="room",
        proves="both",
        requirement={"min_clear_width": "length"},
        checked_exceptions={
            "short-reduction": {
                "reduced_width": "length",
                "max_length": "length",
                "separation_length": "length",
                "separation_width": "length",
            }
        },
    ),
    "accessible_route_exists": CheckSpec(
        function=accessible_route_exists,
        element="room",
        proves="fail_only",
        connectivity="openings_and_rooms",
        uses_check="opening_clear_width",
    ),
}

CHECK_FUNCTIONS: dict[str, Callable[..., Any]] = {name: s.function for name, s in CHECKS.items()}
