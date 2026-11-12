"""Technical checks, one module per check type (spec §9.6).

Every check has the same shape: ``check(model, rule, element, ctx) -> CheckOutcome``. A
check measures; it never decides on its own. The only place a measurement becomes a
verdict is ``plancheck.compliance.verdict``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plancheck.compliance.checks.accessible_route import accessible_route_exists
from plancheck.compliance.checks.corridor_min_width import corridor_min_width
from plancheck.compliance.checks.door_maneuvering_clearance import door_maneuvering_clearance
from plancheck.compliance.checks.opening_clear_width import opening_clear_width
from plancheck.compliance.checks.turning_space import turning_space

CHECK_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "corridor_min_width": corridor_min_width,
    "opening_clear_width": opening_clear_width,
    "door_maneuvering_clearance": door_maneuvering_clearance,
    "turning_space": turning_space,
    "accessible_route_exists": accessible_route_exists,
}
