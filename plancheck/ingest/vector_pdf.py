"""Exact tagged vector-PDF paths/text with explicit plot scale; no raster guessing."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject
from shapely.geometry import Point as ShapePoint
from shapely.geometry import Polygon

from plancheck.ingest.cad import CadEntity, entities_model, model_entities
from plancheck.jurisdiction.extract import extract_pdf_location
from plancheck.model.types import BuildingModel, ProjectContext

SCALE_KEY = "/PlanCheckMillimetresPerPoint"


def export_vector_pdf(model: BuildingModel, path: Path, plot_denominator: float = 100) -> Path:
    if not math.isfinite(plot_denominator) or plot_denominator <= 0:
        raise ValueError("plot scale denominator must be positive")
    scale = 25.4 * plot_denominator / 72
    entities = model_entities(model)
    points = [p for e in entities for p in e.points]
    minx, miny = min(p[0] for p in points), min(p[1] for p in points)
    maxx, maxy = max(p[0] for p in points), max(p[1] for p in points)
    # Preserve the model origin through a declared affine graphics transform.
    ox, oy = 20 - minx / scale, 20 - miny / scale
    writer = PdfWriter()
    page = writer.add_blank_page(
        width=(maxx - minx) / scale + 40, height=(maxy - miny) / scale + 80
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    commands = [f"q {1 / scale:.15g} 0 0 {1 / scale:.15g} {ox:.15g} {oy:.15g} cm"]
    for entity in entities:
        metadata = (
            json.dumps(entity.metadata, ensure_ascii=True, separators=(",", ":")).encode().hex()
        )
        commands.append(f"/PC << /Kind /{entity.kind} /Metadata <{metadata}> >> BDC")
        commands.append(f"{entity.points[0][0]:.15g} {entity.points[0][1]:.15g} m")
        for x, y in entity.points[1:]:
            commands.append(f"{x:.15g} {y:.15g} l")
        if entity.kind in ("room", "boundary", "fixture"):
            commands.append("h")
        commands.extend(["S", "EMC"])
    commands.append("Q")
    for room in model.rooms:
        if room.label:
            label = (
                room.label.encode("ascii", "backslashreplace")
                .decode()
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            center = Polygon(room.clear_polygon).representative_point()
            x, y = center.x / scale + ox, center.y / scale + oy
            commands.append(f"BT /F1 9 Tf 1 0 0 1 {x:.15g} {y:.15g} Tm ({label}) Tj ET")
    commands.append(
        "BT /F1 9 Tf 10 10 Td (PlanCheck exact CAD plot - design assist, not a code review) Tj ET"
    )
    stream = DecodedStreamObject()
    stream.set_data(("\n".join(commands) + "\n").encode("ascii"))
    page.replace_contents(ContentStream(stream, writer))
    writer.add_metadata(
        {
            SCALE_KEY: str(scale),
            "/PlanCheckOriginX": str(ox),
            "/PlanCheckOriginY": str(oy),
            "/Title": "PlanCheck exact CAD plot",
        }
    )
    writer.write(path)
    return path


def import_vector_pdf(
    path: Path, project: ProjectContext | None = None, mm_per_point: float | None = None
) -> BuildingModel:
    reader = PdfReader(path)
    if reader.is_encrypted or len(reader.pages) != 1:
        raise ValueError("exact PDF input must be an unencrypted single floor/page")
    page = reader.pages[0]
    if int(page.get("/Rotate", 0)) % 360 or float(page.get("/UserUnit", 1)) != 1:
        raise ValueError("rotated pages and non-default PDF UserUnit are not supported")
    info: dict[str, Any] = dict(reader.metadata or {})
    stored = info.get(SCALE_KEY)
    scale = (
        mm_per_point if mm_per_point is not None else float(stored) if stored is not None else None
    )
    if scale is None or not math.isfinite(scale) or scale <= 0:
        raise ValueError("PDF plot scale is required; provide millimetres per PDF point")
    if stored is not None and mm_per_point is not None and not math.isclose(float(stored), scale):
        raise ValueError("manual scale conflicts with the PDF's declared scale")
    ox, oy = float(info.get("/PlanCheckOriginX", 0)), float(info.get("/PlanCheckOriginY", 0))
    contents = page.get_contents()
    if contents is None:
        raise ValueError("PDF has no vector content")
    stream = ContentStream(contents, reader)
    matrix = np.eye(3)
    stack = []
    current: dict[str, Any] | None = None
    points: list[tuple[float, float]] = []
    entities = []
    for args, op in stream.operations:
        if op == b"q":
            stack.append(matrix.copy())
        elif op == b"Q":
            if not stack:
                raise ValueError("unbalanced PDF graphics state")
            matrix = stack.pop()
        elif op == b"cm":
            a, b, c, d, e, f = (float(v) for v in args)
            matrix = matrix @ np.array([[a, c, e], [b, d, f], [0, 0, 1]])
        elif op == b"BDC" and args[0] == "/PC":
            if current is not None:
                raise ValueError("nested exact entities are unsupported")
            current = args[1]
            points = []
        elif current is not None and op in (b"m", b"l"):
            if op == b"m" and points:
                raise ValueError("multiple subpaths in one exact entity are unsupported")
            x, y, _ = matrix @ np.array([float(args[0]), float(args[1]), 1])
            points.append(((float(x) - ox) * scale, (float(y) - oy) * scale))
        elif current is not None and op == b"EMC":
            raw = current["/Metadata"]
            data = json.loads(bytes(raw).decode() if isinstance(raw, bytes) else str(raw))
            entities.append(CadEntity(kind=str(current["/Kind"])[1:], points=points, metadata=data))
            current = None
        elif current is not None and op not in (b"S", b"h"):
            raise ValueError(f"unsupported exact path operator {op!r}")
    if current is not None or stack:
        raise ValueError("unbalanced exact PDF content")
    model = entities_model(entities, project)
    labels: dict[str, list[str]] = {}

    def visit_text(text: str, cm: list[float], tm: list[float], font: Any, size: float) -> None:
        value = text.strip()
        if not value:
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        point = ShapePoint((x - ox) * scale, (y - oy) * scale)
        contained = [r.id for r in model.rooms if Polygon(r.clear_polygon).covers(point)]
        if len(contained) == 1:
            labels.setdefault(contained[0], []).append(value)

    page.extract_text(visitor_text=visit_text)
    rooms = []
    for room in model.rooms:
        values = labels.get(room.id, [])
        if len(values) == 1:
            candidate = values[0]
            # The built-in plot font displays non-ASCII labels as escape sequences.
            # Keep the original Unicode metadata when that exact fallback was seen.
            fallback = (
                room.label.encode("ascii", "backslashreplace").decode() if room.label else None
            )
            rooms.append(
                room if candidate == fallback else room.model_copy(update={"label": candidate})
            )
        else:
            rooms.append(room)
    location = extract_pdf_location(path, reader)
    return model.model_copy(
        update={
            "rooms": rooms,
            "scale_source": "pdf_vector",
            "location_extraction": location,
            "warnings": [
                f"Candidate site address (unconfirmed): {item.value}"
                for item in location.candidates
                if item.field == "address"
            ],
        }
    )
