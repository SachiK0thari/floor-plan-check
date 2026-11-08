"""glTF export for the 3D viewer (docs/PROJECT_SPEC.md §12.1).

Walls are extruded from the plan with door and window openings cut. A floor plan has no
heights, so the heights are display defaults, not measurements.

The model is in millimetres with z up. glTF is in metres with y up, so the exporter
converts: (x, y, z) mm becomes (x, z, -y) / 1000 m.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

from plancheck.export.heights import Heights, void_range
from plancheck.model.geometry import opening_gap, polygons, wall_footprint
from plancheck.model.types import BuildingModel

_MM_ZUP_TO_M_YUP = np.array(
    [
        [0.001, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.001, 0.0],
        [0.0, -0.001, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)


def wall_mesh_mm(model: BuildingModel, heights: Heights | None = None) -> trimesh.Trimesh:
    """Walls as one mesh, in millimetres with z up.

    The wall height is cut into horizontal bands at every sill and head height. Within a
    band the plan shape is constant, so each band is a simple extrusion.
    """
    heights = heights or Heights()
    walls = {wall.id: wall for wall in model.walls}
    footprint = unary_union([wall_footprint(wall) for wall in model.walls])
    voids = [
        (opening_gap(walls[o.wall_id], o), void_range(o.kind, heights)) for o in model.openings
    ]
    levels = sorted({0.0, heights.wall_mm, *(z for _, span in voids for z in span)})
    parts = []
    for bottom, top in pairwise(levels):
        active = [gap for gap, (lo, hi) in voids if lo <= bottom and top <= hi]
        plan = footprint.difference(unary_union(active)) if active else footprint
        for polygon in polygons(plan):
            part = trimesh.creation.extrude_polygon(Polygon(polygon), height=top - bottom)
            part.apply_translation((0.0, 0.0, bottom))
            parts.append(part)
    if not parts:
        raise ValueError("model has no walls to export")
    mesh = trimesh.util.concatenate(parts)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def export_gltf(model: BuildingModel, path: str | Path, heights: Heights | None = None) -> Path:
    """Write the model's walls to a binary glTF (.glb) file and return its path."""
    path = Path(path)
    mesh = wall_mesh_mm(model, heights)
    mesh.apply_transform(_MM_ZUP_TO_M_YUP)
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name="walls", geom_name="walls")
    scene.export(str(path), file_type="glb")
    return path
