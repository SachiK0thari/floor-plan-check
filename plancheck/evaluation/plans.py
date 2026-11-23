"""Three analytic review fixtures; these are not author-verified goldens."""

from __future__ import annotations

import math
from datetime import date

from plancheck.model.types import (
    EXTERIOR,
    BuildingModel,
    GraphEdge,
    Measured,
    Opening,
    ProjectContext,
    Room,
    RoomGraph,
    Wall,
)


def exact(value: float) -> Measured:
    return Measured(value_mm=value, sigma_mm=0, source="geometry")


def corridor_plan(
    width: float = 1000,
    door_clear: float | None = 900,
    missing_swing: bool = False,
    room_type: str = "corridor",
) -> BuildingModel:
    top = width + 200
    corners = [(0.0, 0.0), (5200.0, 0.0), (5200.0, top), (0.0, top)]
    walls = [
        Wall(
            id=f"W{i + 1}",
            start=a,
            end=b,
            thickness=exact(200),
            is_exterior=True,
            provenance="synthetic",
        )
        for i, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1], strict=True))
    ]
    room = Room(
        id="C",
        boundary=corners,
        clear_polygon=[(100, 100), (5100, 100), (5100, width + 100), (100, width + 100)],
        room_type=room_type,
        label="Review fixture",
        provenance="synthetic",
    )
    door = Opening(
        id="D",
        kind="door",
        wall_id="W1",
        position_along_wall_mm=2600,
        width=exact(1000),
        leaf_width=exact(950),
        clear_width=exact(door_clear) if door_clear is not None else None,
        operation="swing",
        hinge_at=None if missing_swing else "start",
        swings_to="left",
        provenance="synthetic",
    )
    return BuildingModel(
        walls=walls,
        rooms=[room],
        openings=[door],
        graph=RoomGraph(
            nodes=["C", EXTERIOR], edges=[GraphEdge(opening_id="D", a="C", b=EXTERIOR)]
        ),
        project=ProjectContext(
            facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
        ),
        scale_source="exact",
        scale_rel_sigma=0,
    )


def review_plans() -> dict[str, BuildingModel]:
    return {
        "wide": corridor_plan(),
        "narrow": corridor_plan(800, 700),
        "missing": corridor_plan(1000, None, True, "office").model_copy(
            update={
                "openings": [
                    corridor_plan(1000, None, True, "office")
                    .openings[0]
                    .model_copy(update={"leaf_width": None})
                ]
            }
        ),
    }


def sample_office_plan() -> BuildingModel:
    """A seven-room office suite for demonstrations. Synthetic; not an author-drawn plan.

    The layout comes from the synthetic generator with 36 in door leaves. Door clear
    widths are declared in the model, as a door schedule would give them; they are not
    derived from a deduction. Three conditions are seeded so that each kind of result
    appears: a narrow toilet-room door (fail), an office door whose measured clear width
    is within its uncertainty of the minimum (borderline), and the generator's own
    entrance, which sits too close to a corner for its pull-side clearance (fail).
    """
    from plancheck.synthetic.generator import SyntheticConfig, generate_model

    base = generate_model(3, SyntheticConfig(leaf_widths_mm=(914.4,), max_rooms=7))
    labels = {
        "R01": ("OPEN OFFICE", "office"),
        "R04": ("STORE", "storage"),
        "R06": ("RECEPTION", "reception"),
    }
    rooms = [
        room.model_copy(update={"label": labels[room.id][0], "room_type": labels[room.id][1]})
        if room.id in labels
        else room
        for room in base.rooms
    ]
    seeded: dict[str, dict[str, Measured]] = {
        # A 30 in leaf in place of a 36 in one.
        "D04": {"width": exact(812), "leaf_width": exact(762), "clear_width": exact(710)},
        # Measured on site with a tape: 815 mm, give or take 5 mm.
        "D01": {"clear_width": Measured(value_mm=815, sigma_mm=5, source="user")},
    }
    openings = [
        opening.model_copy(update=seeded.get(opening.id, {"clear_width": exact(860)}))
        if opening.kind == "door"
        else opening
        for opening in base.openings
    ]
    return BuildingModel.model_validate(
        base.model_copy(
            update={
                "rooms": rooms,
                "openings": openings,
                "project": ProjectContext(
                    facility_type="commercial_facility",
                    work_type="new",
                    permit_date=date(2026, 1, 1),
                ),
                "scale_source": "exact",
                "scale_rel_sigma": 0,
            }
        ).model_dump()
    )


def transform_model(
    model: BuildingModel,
    *,
    angle: float = 0,
    dx: float = 0,
    dy: float = 0,
    mirror: bool = False,
    factor: float = 1,
) -> BuildingModel:
    """Transform all geometry coherently; reflected door swing handedness is reversed."""
    if factor <= 0 or not math.isfinite(factor):
        raise ValueError("factor must be finite and positive")
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def point(p: tuple[float, float]) -> tuple[float, float]:
        x, y = p[0] * factor * (-1 if mirror else 1), p[1] * factor
        return (c * x - s * y + dx, s * x + c * y + dy)

    def measured(m: Measured | None) -> Measured | None:
        return (
            m.model_copy(update={"value_mm": m.value_mm * factor, "sigma_mm": m.sigma_mm * factor})
            if m is not None
            else None
        )

    walls = [
        w.model_copy(
            update={
                "start": point(w.start),
                "end": point(w.end),
                "thickness": measured(w.thickness),
            }
        )
        for w in model.walls
    ]
    openings = [
        o.model_copy(
            update={
                "position_along_wall_mm": o.position_along_wall_mm * factor,
                "width": measured(o.width),
                "leaf_width": measured(o.leaf_width),
                "clear_width": measured(o.clear_width),
                "swings_to": (
                    {"left": "right", "right": "left"}.get(o.swings_to)
                    if mirror and o.swings_to
                    else o.swings_to
                ),
            }
        )
        for o in model.openings
    ]
    rooms = [
        r.model_copy(
            update={
                "boundary": [point(p) for p in r.boundary],
                "clear_polygon": [point(p) for p in r.clear_polygon],
                "corridor_paths": [[point(p) for p in path] for path in r.corridor_paths],
            }
        )
        for r in model.rooms
    ]
    fixtures = [
        f.model_copy(update={"footprint": [point(p) for p in f.footprint]}) for f in model.fixtures
    ]
    dimensions = [
        d.model_copy(update={"p1": point(d.p1), "p2": point(d.p2), "value_mm": d.value_mm * factor})
        for d in model.dimensions
    ]
    return BuildingModel.model_validate(
        model.model_copy(
            update={
                "walls": walls,
                "openings": openings,
                "rooms": rooms,
                "fixtures": fixtures,
                "dimensions": dimensions,
            }
        ).model_dump()
    )
