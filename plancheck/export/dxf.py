"""DXF export (docs/PROJECT_SPEC.md §12.1).

Millimetre units, layers named per ``configs/dxf_layers.yaml``, walls as outlines broken
at openings, doors as block references carrying their size as attributes.
"""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon

from plancheck.config import load_config
from plancheck.ingest.dxf import append_exact_entities
from plancheck.model.geometry import door_swing, opening_span, wall_solids
from plancheck.model.types import BuildingModel

DOOR_BLOCK = "PC_DOOR_SWING"
_LABEL_HEIGHT_MM = 200.0


def _define_door_block(doc: Drawing) -> None:
    """Unit swing door: hinge at the origin, closed leaf along +x, open leaf along +y."""
    block = doc.blocks.new(name=DOOR_BLOCK)
    block.add_line((0, 0), (0, 1))
    block.add_arc(center=(0, 0), radius=1, start_angle=0, end_angle=90)


def build_dxf(model: BuildingModel) -> Drawing:
    """The model as an in-memory DXF document."""
    layers = load_config("dxf_layers")
    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.MM  # sets $INSUNITS, so the file opens at the right size
    doc.header["$MEASUREMENT"] = 1  # metric
    for name in dict.fromkeys(layers.values()):
        doc.layers.add(name)
    _define_door_block(doc)
    msp = doc.modelspace()
    walls = {wall.id: wall for wall in model.walls}

    for solid in wall_solids(model):
        for ring in (solid.exterior, *solid.interiors):
            points = [(x, y) for x, y in list(ring.coords)[:-1]]
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layers["wall"]})

    for opening in model.openings:
        wall = walls[opening.wall_id]
        if opening.kind == "window":
            first, second = opening_span(wall, opening)
            nx, ny = wall.left_normal
            half = wall.thickness.value_mm / 2
            for offset in (-half, 0.0, half):
                dx, dy = nx * offset, ny * offset
                msp.add_line(
                    (first[0] + dx, first[1] + dy),
                    (second[0] + dx, second[1] + dy),
                    dxfattribs={"layer": layers["window"]},
                )
        elif opening.kind == "door":
            swing = door_swing(wall, opening)
            if swing is None:
                # Swing not known: mark the door with a line across the opening.
                first, second = opening_span(wall, opening)
                msp.add_line(first, second, dxfattribs={"layer": layers["door"]})
                continue
            # The block's +x maps to `along` and +y to `outward`. When that pair is
            # left-handed the block is mirrored with a negative y scale.
            cross = swing.along[0] * swing.outward[1] - swing.along[1] * swing.outward[0]
            blockref = msp.add_blockref(
                DOOR_BLOCK,
                swing.hinge,
                dxfattribs={
                    "layer": layers["door"],
                    "xscale": swing.leaf_mm,
                    "yscale": swing.leaf_mm if cross > 0 else -swing.leaf_mm,
                    "rotation": math.degrees(math.atan2(swing.along[1], swing.along[0])),
                },
            )
            attribs = {
                "ID": opening.id,
                "TAG": opening.tag or "",
                "LEAF_WIDTH_MM": f"{swing.leaf_mm:.1f}",
                "OPERATION": opening.operation or "",
            }
            for tag, text in attribs.items():
                attrib = blockref.add_attrib(tag, text, swing.hinge, {"layer": layers["door"]})
                attrib.is_invisible = True

    for room in model.rooms:
        msp.add_lwpolyline(
            room.clear_polygon, close=True, dxfattribs={"layer": layers["room_outline"]}
        )
        if room.label:
            centre = Polygon(room.clear_polygon).representative_point()
            label = msp.add_text(
                room.label, height=_LABEL_HEIGHT_MM, dxfattribs={"layer": layers["room_label"]}
            )
            label.set_placement((centre.x, centre.y), align=TextEntityAlignment.MIDDLE_CENTER)
    append_exact_entities(doc, model)
    return doc


def export_dxf(model: BuildingModel, path: str | Path) -> Path:
    """Write the model to a DXF file and return its path."""
    path = Path(path)
    build_dxf(model).saveas(path)
    return path
