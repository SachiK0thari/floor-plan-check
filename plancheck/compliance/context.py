"""Settings a check run needs beyond the model and the rules."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import guard_factor
from plancheck.config import load_config
from plancheck.model.types import BuildingModel, Measured, Opening


def _deductions_from_config() -> dict[str, Measured]:
    """Clear-width deductions from ``configs/verdict.yaml``; unfilled entries are left out."""
    raw: dict[str, Any] = load_config("verdict").get("clear_width_deduction", {})
    out = {}
    for operation, entry in raw.items():
        if entry.get("value") is None:
            continue
        if entry.get("unit", "mm") != "mm":
            raise ValueError("clear_width_deduction values must be in mm")
        out[operation] = Measured(
            value_mm=float(entry["value"]),
            sigma_mm=float(entry.get("sigma") or 0.0),
            source="user",
        )
    return out


@dataclass(frozen=True)
class CheckContext:
    """Guard factor and hardware assumptions. Defaults come from ``configs/verdict.yaml``."""

    k: float = field(default_factory=guard_factor)
    clear_width_deductions: dict[str, Measured] = field(default_factory=_deductions_from_config)
    door_rule: Rule | None = None  # the clear-width rule in this run; route checks reuse it

    def clear_width(self, opening: Opening) -> tuple[Measured | None, str | None]:
        """The opening's clear width, and how it was obtained or why it could not be.

        A measured clear width is used as it is. Otherwise it is the leaf width less the
        configured deduction for the door's operation type (the leaf and the stop both
        sit in the opening when the door is open). For a doorway with no door, the
        deduction key is ``none``.
        """
        if opening.clear_width is not None:
            return opening.clear_width, "clear width as modelled"
        operation = opening.operation or "none"
        deduction = self.clear_width_deductions.get(operation)
        if deduction is None:
            return None, f"clear width not measured and no deduction configured for '{operation}'"
        basis = opening.leaf_width if opening.kind == "door" else opening.width
        if basis is None:
            return None, "door has no leaf width"
        sigma = math.hypot(basis.sigma_mm, deduction.sigma_mm)
        value = Measured(
            value_mm=basis.value_mm - deduction.value_mm, sigma_mm=sigma, source=basis.source
        )
        return value, f"leaf width less the '{operation}' deduction of {deduction.value_mm:g} mm"


def geometry_sigma(model: BuildingModel) -> float:
    """A single uncertainty for positions of wall faces in this model.

    Until vectorization supplies per-wall position uncertainty (M4), the largest wall
    thickness uncertainty stands in for it. Exact models (DXF, synthetic) give zero.
    """
    return max((wall.thickness.sigma_mm for wall in model.walls), default=0.0)


def connectivity_gaps(model: BuildingModel, include_rooms: bool = True) -> list[str]:
    """Elements with no connectivity record; absence is not proof of disconnection."""
    connected = {edge.opening_id for edge in model.graph.edges}
    missing = [
        opening.id
        for opening in model.openings
        if opening.kind in ("door", "opening") and opening.id not in connected
    ]
    if include_rooms:
        missing.extend(room.id for room in model.rooms if room.id not in model.graph.nodes)
    return sorted(missing)
