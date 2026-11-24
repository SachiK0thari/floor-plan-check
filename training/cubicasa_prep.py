"""Convert CubiCasa5K annotations into label masks for segmentation training.

CubiCasa5K stores each plan as ``<plan>/F1_scaled.png`` plus ``<plan>/model.svg``. The SVG
coordinates are pixels of ``F1_scaled.png``. One image can show several drawings; each is a
``Floorplan`` group in the SVG, and all of them are drawn onto the same image.

Output, under ``--out``:

- ``images/<id>.png``: the plan image, resized so its long side is at most ``--max-side``.
- ``room/<id>.png``: 0 background, 1 wall, 2 railing, 3+ space type (see ``vocab.json``).
- ``icon/<id>.png``: 0 none, 1 door, 2 window, 3+ fixed furniture type (see ``vocab.json``).
- ``index.jsonl``: one line per plan with its split, source folder, original size and the scale
  from original pixels to stored pixels, so image-to-model transforms stay exact.
- ``vocab.json``: label ids and counts, assigned from a first pass over every annotation.

Self-contained (standard library, numpy, Pillow) so it runs unchanged as a Kaggle script.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw

Matrix = tuple[float, float, float, float, float, float]  # SVG order: a b c d e f
Point = tuple[float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

ROOM_WALL = 1
ROOM_RAILING = 2
ROOM_FIRST_SPACE = 3
ICON_DOOR = 1
ICON_WINDOW = 2
ICON_FIRST_FURNITURE = 3
MAX_LABELS = 255  # masks are 8-bit

SPLITS = ("train", "val", "test")
IMAGE_NAME = "F1_scaled.png"
SVG_NAME = "model.svg"

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


@dataclass(frozen=True)
class Shape:
    """One annotated polygon, in image pixel coordinates."""

    kind: str  # space, wall, railing, door, window, furniture
    label: str  # space or furniture type; "" for the other kinds
    points: tuple[Point, ...]


# ---------------------------------------------------------------------------
# SVG parsing
# ---------------------------------------------------------------------------


def multiply(m: Matrix, n: Matrix) -> Matrix:
    """Return m·n: apply n first, then m."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def parse_transform(text: str | None) -> Matrix:
    """Parse an SVG ``transform`` attribute into one matrix."""
    result = IDENTITY
    if not text:
        return result
    for name, args in _TRANSFORM.findall(text):
        v = [float(x) for x in _NUMBER.findall(args)]
        if name == "matrix" and len(v) == 6:
            m: Matrix = (v[0], v[1], v[2], v[3], v[4], v[5])
        elif name == "translate" and v:
            m = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale" and v:
            m = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "rotate" and v:
            t = math.radians(v[0])
            cos, sin = math.cos(t), math.sin(t)
            m = (cos, sin, -sin, cos, 0.0, 0.0)
            if len(v) == 3:
                cx, cy = v[1], v[2]
                m = multiply(multiply((1, 0, 0, 1, cx, cy), m), (1, 0, 0, 1, -cx, -cy))
        elif name == "skewX" and v:
            m = (1.0, 0.0, math.tan(math.radians(v[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and v:
            m = (1.0, math.tan(math.radians(v[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise ValueError(f"unsupported transform {name}({args})")
        result = multiply(result, m)
    return result


def apply(m: Matrix, p: Point) -> Point:
    a, b, c, d, e, f = m
    x, y = p
    return (a * x + c * y + e, b * x + d * y + f)


def parse_points(text: str | None) -> list[Point]:
    """Parse a polygon ``points`` attribute; tolerates any comma and space layout."""
    v = [float(x) for x in _NUMBER.findall(text or "")]
    return list(zip(v[0::2], v[1::2], strict=False))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str, cls: str | None = None) -> ET.Element | None:
    for ch in element:
        if _local(ch.tag) == name and (cls is None or (ch.get("class") or "").split()[:1] == [cls]):
            return ch
    return None


def _shape_of(element: ET.Element) -> tuple[str, str, ET.Element | None] | None:
    """Return (kind, label, polygon element) for an annotated group, or None."""
    words = (element.get("class") or "").split()
    if not words:
        return None
    head, rest = words[0], " ".join(words[1:])
    if head == "Space":
        return "space", rest or "Undefined", _child(element, "polygon")
    if head == "Wall":
        return "wall", "", _child(element, "polygon")
    if head == "Railing":
        return "railing", "", _child(element, "polygon")
    if head == "Door":
        return "door", "", _child(element, "polygon")
    if head == "Window":
        return "window", "", _child(element, "polygon")
    if head == "FixedFurniture":
        boundary = _child(element, "g", "BoundaryPolygon")
        polygon = _child(boundary, "polygon") if boundary is not None else None
        # The boundary group may carry its own transform.
        return "furniture", rest or "Undefined", polygon
    return None


def read_shapes(svg_text: str) -> list[Shape]:
    """Every annotated polygon in a CubiCasa SVG, with transforms applied, in document order."""
    root = ET.fromstring(svg_text)
    shapes: list[Shape] = []

    def walk(element: ET.Element, ctm: Matrix) -> None:
        ctm = multiply(ctm, parse_transform(element.get("transform")))
        found = _shape_of(element)
        if found is not None:
            kind, label, polygon = found
            if polygon is not None:
                m = ctm
                if kind == "furniture":
                    boundary = _child(element, "g", "BoundaryPolygon")
                    if boundary is not None:
                        m = multiply(m, parse_transform(boundary.get("transform")))
                m = multiply(m, parse_transform(polygon.get("transform")))
                pts = parse_points(polygon.get("points"))
                if len(pts) >= 3:
                    shapes.append(Shape(kind, label, tuple(apply(m, p) for p in pts)))
            if kind == "furniture":
                return  # nested furniture parts are drawing detail, not separate items
        for ch in element:
            walk(ch, ctm)

    walk(root, IDENTITY)
    return shapes


# ---------------------------------------------------------------------------
# Vocabulary and rasterization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Vocab:
    spaces: dict[str, int]
    furniture: dict[str, int]
    space_counts: dict[str, int]
    furniture_counts: dict[str, int]

    def to_json(self) -> dict[str, object]:
        return {
            "room": {"0": "background", str(ROOM_WALL): "wall", str(ROOM_RAILING): "railing"}
            | {str(i): f"space:{n}" for n, i in self.spaces.items()},
            "icon": {"0": "none", str(ICON_DOOR): "door", str(ICON_WINDOW): "window"}
            | {str(i): f"furniture:{n}" for n, i in self.furniture.items()},
            "space_counts": self.space_counts,
            "furniture_counts": self.furniture_counts,
        }


def build_vocab(space_counts: Counter[str], furniture_counts: Counter[str]) -> Vocab:
    """Assign ids by descending count, then name, so the result does not depend on file order."""

    def ids(counts: Counter[str], first: int) -> dict[str, int]:
        names = sorted(counts, key=lambda n: (-counts[n], n))
        if first + len(names) > MAX_LABELS + 1:
            raise ValueError(f"{len(names)} labels do not fit in an 8-bit mask")
        return {n: first + i for i, n in enumerate(names)}

    return Vocab(
        spaces=ids(space_counts, ROOM_FIRST_SPACE),
        furniture=ids(furniture_counts, ICON_FIRST_FURNITURE),
        space_counts=dict(sorted(space_counts.items())),
        furniture_counts=dict(sorted(furniture_counts.items())),
    )


def rasterize(
    shapes: Sequence[Shape], size: tuple[int, int], scale: float, vocab: Vocab
) -> tuple[Image.Image, Image.Image]:
    """Draw the room and icon masks at ``size`` (width, height), scaling coordinates by ``scale``.

    Room mask order: spaces, then railings, then walls, so walls win where they overlap a
    space. Icon mask order: furniture, then windows, then doors.
    """
    room = Image.new("L", size, 0)
    icon = Image.new("L", size, 0)
    rd, idr = ImageDraw.Draw(room), ImageDraw.Draw(icon)

    def pts(s: Shape) -> list[Point]:
        return [(x * scale, y * scale) for x, y in s.points]

    passes: list[tuple[ImageDraw.ImageDraw, str, int | None]] = [
        (rd, "space", None),
        (rd, "railing", ROOM_RAILING),
        (rd, "wall", ROOM_WALL),
        (idr, "furniture", None),
        (idr, "window", ICON_WINDOW),
        (idr, "door", ICON_DOOR),
    ]
    for draw, kind, value in passes:
        for s in shapes:
            if s.kind != kind:
                continue
            if value is not None:
                fill = value
            elif kind == "space":
                fill = vocab.spaces[s.label]
            else:
                fill = vocab.furniture[s.label]
            draw.polygon(pts(s), fill=fill)
    return room, icon


# ---------------------------------------------------------------------------
# Dataset walk
# ---------------------------------------------------------------------------


def find_root(base: Path) -> Path:
    """The folder holding train.txt, val.txt and test.txt (Kaggle nests the dataset)."""
    if (base / "train.txt").is_file():
        return base
    for found in sorted(base.rglob("train.txt")):
        return found.parent
    raise FileNotFoundError(f"no train.txt under {base}")


def read_splits(root: Path) -> Iterator[tuple[str, str]]:
    """Yield (split, plan folder relative to root) from the official split files."""
    for split in SPLITS:
        for line in (root / f"{split}.txt").read_text().split():
            yield split, line.strip("/")


def plan_id(folder: str) -> str:
    return folder.strip("/").replace("/", "__")


def count_labels(root: Path, folders: Iterable[str]) -> tuple[Counter[str], Counter[str]]:
    spaces: Counter[str] = Counter()
    furniture: Counter[str] = Counter()
    for folder in folders:
        for s in read_shapes((root / folder / SVG_NAME).read_text(encoding="utf-8")):
            if s.kind == "space":
                spaces[s.label] += 1
            elif s.kind == "furniture":
                furniture[s.label] += 1
    return spaces, furniture


def _count_one(args: tuple[str, str]) -> tuple[Counter[str], Counter[str], str | None]:
    root, folder = args
    try:
        spaces, furniture = count_labels(Path(root), [folder])
    except (OSError, ValueError, ET.ParseError) as exc:
        return Counter(), Counter(), f"{folder}: {type(exc).__name__}: {exc}"
    return spaces, furniture, None


def _convert_one(args: tuple[str, str, str, str, int, Vocab]) -> dict[str, object]:
    root, out, split, folder, max_side, vocab = args
    try:
        return _convert(root, out, split, folder, max_side, vocab)
    except (OSError, ValueError, ET.ParseError) as exc:
        return {"source": folder, "split": split, "error": f"{type(exc).__name__}: {exc}"}


def _convert(
    root: str, out: str, split: str, folder: str, max_side: int, vocab: Vocab
) -> dict[str, object]:
    src = Path(root) / folder
    image = Image.open(src / IMAGE_NAME).convert("RGB")
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    if scale < 1.0:
        image = image.resize(size, Image.Resampling.LANCZOS)
    shapes = read_shapes((src / SVG_NAME).read_text(encoding="utf-8"))
    room, icon = rasterize(shapes, size, scale, vocab)
    pid = plan_id(folder)
    image.save(Path(out) / "images" / f"{pid}.png")
    room.save(Path(out) / "room" / f"{pid}.png")
    icon.save(Path(out) / "icon" / f"{pid}.png")
    return {
        "id": pid,
        "split": split,
        "source": folder,
        "original_size": [width, height],
        "size": list(size),
        "scale": scale,
        "shapes": dict(Counter(s.kind for s in shapes)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True, help="CubiCasa5K folder (any parent)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-side", type=int, default=2048)
    parser.add_argument("--limit", type=int, default=0, help="convert only N plans (smoke test)")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args(argv)

    root = find_root(args.data)
    plans = list(read_splits(root))
    if args.limit:
        plans = plans[: args.limit]
    for sub in ("images", "room", "icon"):
        (args.out / sub).mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, object]] = []
    with Pool(args.workers) as pool:
        spaces: Counter[str] = Counter()
        furniture: Counter[str] = Counter()
        unreadable: set[str] = set()
        for s, f, err in pool.imap_unordered(_count_one, [(str(root), p) for _, p in plans], 32):
            spaces.update(s)
            furniture.update(f)
            if err:
                unreadable.add(err.split(":", 1)[0])
        vocab = build_vocab(spaces, furniture)
        (args.out / "vocab.json").write_text(json.dumps(vocab.to_json(), indent=2))
        print(f"vocab: {len(vocab.spaces)} space types, {len(vocab.furniture)} furniture types")

        jobs = [
            (str(root), str(args.out), sp, p, args.max_side, vocab)
            for sp, p in plans
            if p not in unreadable
        ]
        errors += [
            {"source": p, "split": sp, "error": "unreadable annotation"}
            for sp, p in plans
            if p in unreadable
        ]
        rows: list[dict[str, object]] = []
        for i, row in enumerate(pool.imap_unordered(_convert_one, jobs, 8), 1):
            (errors if "error" in row else rows).append(row)
            if i % 250 == 0 or i == len(jobs):
                print(f"converted {i}/{len(jobs)}", flush=True)
    rows.sort(key=lambda r: (SPLITS.index(str(r["split"])), str(r["id"])))
    with (args.out / "index.jsonl").open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    with (args.out / "errors.jsonl").open("w") as fh:
        for row in errors:
            fh.write(json.dumps(row) + "\n")
    print("splits:", dict(Counter(str(r["split"]) for r in rows)), "failed:", len(errors))
    for row in errors[:20]:
        print("  failed:", row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
