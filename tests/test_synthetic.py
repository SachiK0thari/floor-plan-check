from __future__ import annotations

import random

import networkx as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from plancheck.model.geometry import drawing_bounds
from plancheck.model.types import EXTERIOR, BuildingModel
from plancheck.synthetic.generator import SyntheticConfig, catalog_leaf_widths_mm, generate_model
from plancheck.synthetic.render import RenderStyle, random_style, render

SEEDS = range(40)


def test_catalog_widths_are_converted_to_mm() -> None:
    widths = catalog_leaf_widths_mm("us_nominal")
    assert widths[0] == pytest.approx(609.6)  # 24 in
    assert widths[-1] == pytest.approx(914.4)  # 36 in


def test_same_seed_gives_same_plan() -> None:
    assert generate_model(7) == generate_model(7)
    assert generate_model(7) != generate_model(8)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_room_reaches_the_exterior(seed: int) -> None:
    model = generate_model(seed)
    graph = model.graph.to_networkx()
    assert set(graph.nodes) == {room.id for room in model.rooms} | {EXTERIOR}
    assert nx.is_connected(graph)


@pytest.mark.parametrize("seed", SEEDS)
def test_rooms_tile_the_outline(seed: int) -> None:
    model = generate_model(seed)
    boundaries = [Polygon(room.boundary) for room in model.rooms]
    outline = unary_union(boundaries)
    exterior = [w for w in model.walls if w.is_exterior]
    width, depth = exterior[0].length_mm, exterior[1].length_mm
    assert outline.area == pytest.approx(width * depth)
    assert sum(b.area for b in boundaries) == pytest.approx(outline.area)  # no overlaps
    for room in model.rooms:
        assert 0 < room.area_net_m2 < room.area_gross_m2


@pytest.mark.parametrize("seed", SEEDS)
def test_doors_use_catalog_sizes_and_join_adjacent_rooms(seed: int) -> None:
    model = generate_model(seed)
    catalog = catalog_leaf_widths_mm()
    doors = [o for o in model.openings if o.kind == "door"]
    assert {edge.opening_id for edge in model.graph.edges} == {door.id for door in doors}
    for door in doors:
        assert door.leaf_width is not None
        assert door.leaf_width.value_mm in catalog
    for edge in model.graph.edges:
        # The door's centre must sit on the boundary of every room it connects.
        door = model.opening(edge.opening_id)
        centre = model.wall(door.wall_id).point_at(door.position_along_wall_mm)
        for node in (edge.a, edge.b):
            if node != EXTERIOR:
                boundary = Polygon(model.room(node).boundary).exterior
                assert boundary.distance(Point(centre)) < 1e-6


@given(seed=st.integers(min_value=0, max_value=10**6))
@settings(max_examples=30, deadline=None)
def test_generated_models_survive_json(seed: int) -> None:
    model = generate_model(seed)
    assert BuildingModel.model_validate_json(model.model_dump_json()) == model


def test_generator_respects_config() -> None:
    cfg = SyntheticConfig(max_rooms=2, leaf_widths_mm=(800.0,), window_prob=0.0)
    model = generate_model(3, cfg)
    assert len(model.rooms) == 2
    assert all(o.kind == "door" and o.leaf_width.value_mm == 800.0 for o in model.openings)  # type: ignore[union-attr]


# ---------------------------------------------------------------- rendering


def test_render_scale_and_transform_are_exact() -> None:
    model = generate_model(1)
    style = RenderStyle(px_per_mm=0.1, margin_px=40, show_labels=False)
    image, placed = render(model, style)
    minx, miny, maxx, maxy = drawing_bounds(model)
    assert image.size == (round((maxx - minx) * 0.1) + 80, round((maxy - miny) * 0.1) + 80)
    assert placed.px_per_mm == 0.1
    assert placed.scale_source == "exact"
    transform = placed.image_to_model
    assert transform is not None
    assert transform.kind == "affine"
    # Bottom-left of the drawing is at the left margin, one margin up from the bottom edge.
    assert transform.apply((40.0, image.size[1] - 40.0)) == pytest.approx((minx, miny))
    assert transform.apply((image.size[0] - 40.0, 40.0)) == pytest.approx((maxx, maxy))


def test_render_draws_walls_dark_and_rooms_light() -> None:
    model = generate_model(1)
    image, placed = render(model, RenderStyle(wall_style="solid", show_labels=False))
    assert placed.image_to_model is not None
    to_px = placed.image_to_model.inverse()

    # A point on an exterior wall centerline, away from corners and openings.
    wall = next(w for w in model.walls if w.is_exterior)
    taken = [
        (o.position_along_wall_mm - o.width.value_mm, o.position_along_wall_mm + o.width.value_mm)
        for o in model.openings
        if o.wall_id == wall.id
    ]
    distance = next(
        d
        for d in range(300, int(wall.length_mm) - 300, 50)
        if all(not lo <= d <= hi for lo, hi in taken)
    )
    x, y = to_px.apply(wall.point_at(distance))
    assert image.getpixel((round(x), round(y))) == 0

    # The centre of a room is floor, well clear of any door swing for these room sizes.
    for room in model.rooms:
        centre = Polygon(room.clear_polygon).centroid
        x, y = to_px.apply((centre.x, centre.y))
        assert image.getpixel((round(x), round(y))) == 255


@pytest.mark.parametrize("seed", range(10))
def test_render_works_in_every_random_style(seed: int) -> None:
    rng = random.Random(seed)
    image, placed = render(generate_model(seed), random_style(rng))
    assert image.mode == "L"
    assert image.getextrema()[0] == 0  # something was drawn
    assert placed.image_to_model is not None


@pytest.mark.parametrize("seed", range(20))
def test_render_keeps_door_swings_inside_the_margin(seed: int) -> None:
    # Outward-opening exterior doors reach past the walls; nothing may be drawn in the margin.
    style = RenderStyle(margin_px=30, show_labels=False)
    image, _ = render(generate_model(seed), style)
    left, top, right, bottom = image.point(lambda v: 255 - v).getbbox() or (0, 0, 0, 0)
    assert left >= 29
    assert top >= 29
    assert right <= image.size[0] - 29
    assert bottom <= image.size[1] - 29
