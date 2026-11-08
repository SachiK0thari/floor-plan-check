"""Display heights shared by the 3D exporters.

A floor plan has no heights. These are defaults for viewing only, not measurements, and
no compliance check reads them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Heights:
    """Display heights in millimetres."""

    wall_mm: float = 2700.0
    door_head_mm: float = 2100.0
    window_sill_mm: float = 900.0
    window_head_mm: float = 2100.0


def void_range(kind: str, heights: Heights) -> tuple[float, float]:
    """The height range over which an opening of this kind removes wall."""
    if kind == "window":
        return (heights.window_sill_mm, min(heights.window_head_mm, heights.wall_mm))
    if kind == "door":
        return (0.0, min(heights.door_head_mm, heights.wall_mm))
    return (0.0, heights.wall_mm)  # cased opening: full height
