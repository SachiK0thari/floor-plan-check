"""Draw a BuildingModel as a raster floor plan, in a randomizable drawing style."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon

from plancheck.model.geometry import door_swing, drawing_bounds, opening_span, wall_solids
from plancheck.model.types import BuildingModel, Point, Transform

_BLACK, _WHITE = 0, 255
_ARC_STEPS = 16


@dataclass(frozen=True)
class RenderStyle:
    px_per_mm: float = 0.1
    margin_px: int = 40
    wall_style: Literal["solid", "hollow"] = "solid"
    line_px: int = 2
    door_style: Literal["arc", "leaf"] = "arc"
    show_labels: bool = True
    label_px: int = 14


def random_style(rng: random.Random) -> RenderStyle:
    """A drawing style picked at random, to vary how the same plan looks."""
    return RenderStyle(
        px_per_mm=rng.choice((0.06, 0.08, 0.1, 0.125)),
        margin_px=rng.randint(20, 80),
        wall_style=rng.choice(("solid", "hollow")),
        line_px=rng.randint(1, 3),
        door_style=rng.choice(("arc", "leaf")),
        show_labels=rng.random() < 0.8,
        label_px=rng.randint(11, 18),
    )


def render(
    model: BuildingModel, style: RenderStyle | None = None
) -> tuple[Image.Image, BuildingModel]:
    """Draw the model. Returns the image and the model with its image transform and scale set."""
    style = style or RenderStyle()
    scale, margin = style.px_per_mm, style.margin_px
    minx, miny, maxx, maxy = drawing_bounds(model)
    width = math.ceil((maxx - minx) * scale) + 2 * margin
    height = math.ceil((maxy - miny) * scale) + 2 * margin

    def to_px(point: Point) -> Point:
        return ((point[0] - minx) * scale + margin, height - ((point[1] - miny) * scale + margin))

    image = Image.new("L", (width, height), _WHITE)
    draw = ImageDraw.Draw(image)
    walls = {wall.id: wall for wall in model.walls}

    # Outer polygons first: the building's interior is a hole in the exterior wall ring,
    # and it has to be painted white before the interior walls inside it are drawn.
    fill = _BLACK if style.wall_style == "solid" else _WHITE
    for solid in sorted(wall_solids(model), key=lambda p: p.envelope.area, reverse=True):
        outer = [to_px(p) for p in solid.exterior.coords]
        draw.polygon(outer, fill=fill, outline=_BLACK, width=style.line_px)
        for ring in solid.interiors:
            draw.polygon(
                [to_px(p) for p in ring.coords], fill=_WHITE, outline=_BLACK, width=style.line_px
            )

    for opening in model.openings:
        wall = walls[opening.wall_id]
        if opening.kind == "window":
            first, second = opening_span(wall, opening)
            nx, ny = wall.left_normal
            half = wall.thickness.value_mm / 2
            for offset in (-half, 0.0, half):
                shift = (nx * offset, ny * offset)
                draw.line(
                    [
                        to_px((first[0] + shift[0], first[1] + shift[1])),
                        to_px((second[0] + shift[0], second[1] + shift[1])),
                    ],
                    fill=_BLACK,
                    width=1,
                )
            continue
        swing = door_swing(wall, opening)
        if swing is None:
            continue
        draw.line([to_px(swing.hinge), to_px(swing.tip)], fill=_BLACK, width=style.line_px)
        if style.door_style == "arc":
            arc = []
            for step in range(_ARC_STEPS + 1):
                angle = (math.pi / 2) * step / _ARC_STEPS
                along, outward = math.cos(angle) * swing.leaf_mm, math.sin(angle) * swing.leaf_mm
                arc.append(
                    to_px(
                        (
                            swing.hinge[0] + swing.along[0] * along + swing.outward[0] * outward,
                            swing.hinge[1] + swing.along[1] * along + swing.outward[1] * outward,
                        )
                    )
                )
            draw.line(arc, fill=_BLACK, width=1)

    if style.show_labels:
        font = ImageFont.load_default(size=style.label_px)
        for room in model.rooms:
            if room.label:
                centre = Polygon(room.clear_polygon).representative_point()
                draw.text(
                    to_px((centre.x, centre.y)), room.label, fill=_BLACK, font=font, anchor="mm"
                )

    # Inverse of to_px: pixel (x right, y down) to plan millimetres.
    transform = Transform(
        matrix=(
            (1 / scale, 0.0, minx - margin / scale),
            (0.0, -1 / scale, miny + (height - margin) / scale),
            (0.0, 0.0, 1.0),
        )
    )
    placed = model.model_copy(
        update={
            "image_to_model": transform,
            "px_per_mm": scale,
            "scale_rel_sigma": 0.0,
            "scale_x_over_y": 1.0,
            "scale_source": "exact",
        }
    )
    return image, placed
