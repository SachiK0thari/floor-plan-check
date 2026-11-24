"""Known-answer tests for the CubiCasa5K annotation converter.

The SVGs here are written by hand in the CubiCasa layout; no dataset file is used.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from training import cubicasa_prep as prep

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80">
<g class="Model">
 <g class="Floor">
  <g class="Floorplan Floor-1" id="Floor-1" transform="matrix(1,0,0,1,0,0)">
   <g class="Space Kitchen"><polygon points="10,10 50,10 50,50 10,50 "/></g>
   <g class="Wall External"><polygon points="8,8 52,8 52,12 8,12"/>
    <g class="Door Swing Beside"><polygon points="20,8 30,8 30,12 20,12"/>
     <g class="Threshold"><polygon points="20,8 30,8 30,12 20,12"/></g></g>
    <g class="Window Regular"><polygon points="35,8 45,8 45,12 35,12"/></g>
   </g>
   <g class="Railing"><polygon points="60,10 62,10 62,40 60,40"/></g>
   <g class="FixedFurniture Toilet" transform="matrix(1,0,0,1,15,30)">
    <g class="BoundaryPolygon"><polygon points="0,0 6,0 6,8 0,8"/></g>
    <g class="FixedFurniture Seat">
     <g class="BoundaryPolygon"><polygon points="0,0 1,0 1,1"/></g></g>
   </g>
   <g class="Space Undefined"><polygon points="1,1 2,2"/></g>
  </g>
 </g>
 <g class="Floor" style="display: none;">
  <g class="Floorplan Floor-2" id="Floor-2" transform="translate(70,0)">
   <g class="Space"><polygon points="0,50 20,50 20,70 0,70"/></g>
  </g>
 </g>
</g>
</svg>"""


def close(p: tuple[float, float], q: tuple[float, float]) -> bool:
    return math.isclose(p[0], q[0], abs_tol=1e-9) and math.isclose(p[1], q[1], abs_tol=1e-9)


def test_parse_points_tolerates_layouts() -> None:
    assert prep.parse_points("1,2 3,4 ") == [(1.0, 2.0), (3.0, 4.0)]
    assert prep.parse_points("1 2,3 4") == [(1.0, 2.0), (3.0, 4.0)]
    assert prep.parse_points("-1.5e1,2 .5,-3") == [(-15.0, 2.0), (0.5, -3.0)]
    assert prep.parse_points(None) == []


def test_parse_transform_known_answers() -> None:
    assert prep.parse_transform(None) == prep.IDENTITY
    assert close(prep.apply(prep.parse_transform("translate(5,6)"), (1, 1)), (6, 7))
    assert close(prep.apply(prep.parse_transform("scale(2)"), (1, 3)), (2, 6))
    # SVG applies the rightmost transform first: scale, then translate.
    m = prep.parse_transform("translate(10,0) scale(2)")
    assert close(prep.apply(m, (1, 1)), (12, 2))
    assert close(prep.apply(prep.parse_transform("rotate(90)"), (1, 0)), (0, 1))
    assert close(prep.apply(prep.parse_transform("rotate(90 10 10)"), (11, 10)), (10, 11))
    assert close(prep.apply(prep.parse_transform("matrix(1,0,0,1,3,4)"), (0, 0)), (3, 4))


def test_parse_transform_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        prep.parse_transform("matrix(1,2)")


def test_read_shapes_finds_every_annotation() -> None:
    shapes = prep.read_shapes(SVG)
    kinds = Counter(s.kind for s in shapes)
    # The two-point space is skipped; the nested furniture part is not a separate item.
    assert kinds == Counter(space=2, wall=1, door=1, window=1, railing=1, furniture=1)
    labels = {(s.kind, s.label) for s in shapes}
    assert ("space", "Kitchen") in labels
    assert ("space", "Undefined") in labels  # a bare "Space" class
    assert ("furniture", "Toilet") in labels


def test_read_shapes_applies_transforms() -> None:
    shapes = prep.read_shapes(SVG)
    toilet = next(s for s in shapes if s.kind == "furniture")
    assert toilet.points[0] == (15.0, 30.0)
    assert toilet.points[2] == (21.0, 38.0)
    # The hidden second floor is still drawn, shifted by its group transform.
    second = next(s for s in shapes if s.kind == "space" and s.label == "Undefined")
    assert second.points[0] == (70.0, 50.0)


def test_build_vocab_orders_by_count_then_name() -> None:
    vocab = prep.build_vocab(Counter(b=2, a=2, c=5), Counter(x=1))
    assert vocab.spaces == {"c": 3, "a": 4, "b": 5}
    assert vocab.furniture == {"x": 3}
    room = vocab.to_json()["room"]
    assert isinstance(room, dict)
    assert room["1"] == "wall"
    assert room["3"] == "space:c"


def test_build_vocab_rejects_too_many_labels() -> None:
    with pytest.raises(ValueError, match="8-bit"):
        prep.build_vocab(Counter({str(i): 1 for i in range(300)}), Counter())


def test_rasterize_layers_and_scale() -> None:
    shapes = prep.read_shapes(SVG)
    vocab = prep.build_vocab(Counter(Kitchen=1, Undefined=1), Counter(Toilet=1))
    room, icon = prep.rasterize(shapes, (100, 80), 1.0, vocab)
    assert room.getpixel((30, 30)) == vocab.spaces["Kitchen"]
    assert room.getpixel((30, 10)) == prep.ROOM_WALL  # wall drawn over the space
    assert room.getpixel((61, 20)) == prep.ROOM_RAILING
    assert room.getpixel((5, 5)) == 0
    assert icon.getpixel((25, 10)) == prep.ICON_DOOR
    assert icon.getpixel((40, 10)) == prep.ICON_WINDOW
    assert icon.getpixel((18, 34)) == vocab.furniture["Toilet"]
    assert icon.getpixel((30, 30)) == 0

    half_room, _ = prep.rasterize(shapes, (50, 40), 0.5, vocab)
    assert half_room.size == (50, 40)
    assert half_room.getpixel((15, 15)) == vocab.spaces["Kitchen"]
    assert half_room.getpixel((15, 5)) == prep.ROOM_WALL


def make_dataset(base: Path) -> Path:
    root = base / "nested" / "cubicasa5k"
    for folder, split in (("high_quality/1", "train"), ("colorful/2", "test")):
        d = root / folder
        d.mkdir(parents=True)
        (d / prep.SVG_NAME).write_text(SVG, encoding="utf-8")
        Image.new("RGB", (200, 160), "white").save(d / prep.IMAGE_NAME)
        with (root / f"{split}.txt").open("a") as fh:
            fh.write(f"/{folder}/\n")
    (root / "val.txt").write_text("")
    return root


def test_find_root_and_splits(tmp_path: Path) -> None:
    root = make_dataset(tmp_path)
    assert prep.find_root(tmp_path) == root
    assert list(prep.read_splits(root)) == [("train", "high_quality/1"), ("test", "colorful/2")]
    assert prep.plan_id("/high_quality/1/") == "high_quality__1"
    with pytest.raises(FileNotFoundError):
        prep.find_root(tmp_path / "nested" / "cubicasa5k" / "colorful")


def test_main_converts_and_resizes(tmp_path: Path) -> None:
    make_dataset(tmp_path / "data")
    out = tmp_path / "out"
    code = prep.main(["--data", str(tmp_path / "data"), "--out", str(out), "--max-side", "100"])
    assert code == 0
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == ["high_quality__1", "colorful__2"]
    assert rows[0]["scale"] == 0.5
    assert rows[0]["original_size"] == [200, 160]
    assert rows[0]["size"] == [100, 80]
    room = Image.open(out / "room" / "high_quality__1.png")
    assert room.size == (100, 80)
    vocab = json.loads((out / "vocab.json").read_text())
    assert vocab["space_counts"] == {"Kitchen": 2, "Undefined": 2}
    assert room.getpixel((15, 15)) == 3  # Kitchen and Undefined tie at 2; Kitchen sorts first
    assert (out / "errors.jsonl").read_text() == ""


def test_main_records_failures_and_continues(tmp_path: Path) -> None:
    root = make_dataset(tmp_path / "data")
    (root / "colorful" / "2" / prep.SVG_NAME).write_text("<svg", encoding="utf-8")
    (root / "high_quality" / "1" / prep.IMAGE_NAME).unlink()
    (root / "val.txt").write_text("/missing/3/\n")
    out = tmp_path / "out"
    assert prep.main(["--data", str(tmp_path / "data"), "--out", str(out), "--workers", "1"]) == 0
    errors = [json.loads(line) for line in (out / "errors.jsonl").read_text().splitlines()]
    assert sorted(str(e["source"]) for e in errors) == ["colorful/2", "high_quality/1", "missing/3"]
    assert (out / "index.jsonl").read_text() == ""


def test_kaggle_push_builds_script_with_driver(tmp_path: Path) -> None:
    from training import kaggle_push

    meta_path = kaggle_push.build(kaggle_push.JOBS["prep"], "someone", tmp_path)
    meta = json.loads(meta_path.read_text())
    assert meta["id"] == "someone/plancheck-cubicasa-prep"
    assert meta["dataset_sources"] == ["qmarva/cubicasa5k"]
    assert meta["is_private"] is True
    code = (tmp_path / "cubicasa_prep.py").read_text()
    assert code.count('if __name__ == "__main__":') == 1
    assert "cubicasa_masks.tar" in code
    compile(code, "cubicasa_prep.py", "exec")
