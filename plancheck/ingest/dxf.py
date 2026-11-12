"""Strict PlanCheck exact-CAD DXF import, with explicit millimetre dimensional metadata."""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity, Line, LWPolyline, Point, Text
from ezdxf.enums import InsertUnits
from shapely.geometry import Point as ShapePoint
from shapely.geometry import Polygon

from plancheck.config import load_config
from plancheck.ingest.cad import CadEntity, entities_model, model_entities
from plancheck.jurisdiction.extract import extract_dxf_location
from plancheck.model.types import BuildingModel, ProjectContext

APP = "PLANCHECK_EXACT_V1"
LAYERS = {
    kind: f"PC-{kind.upper()}"
    for kind in ("wall", "opening", "room", "boundary", "route", "fixture", "dimension")
}


def append_exact_entities(doc: Drawing, model: BuildingModel) -> None:
    if not doc.units:
        raise ValueError("DXF must declare units")
    factor = units.conversion_factor(InsertUnits.Millimeters, InsertUnits(doc.units))
    if APP not in doc.appids:
        doc.appids.new(APP)
    for layer in LAYERS.values():
        if layer not in doc.layers:
            doc.layers.new(layer, dxfattribs={"plot": 0})
    drawn: DXFEntity
    for entity in model_entities(model):
        points = [(x * factor, y * factor) for x, y in entity.points]
        attrs = {"layer": LAYERS[entity.kind]}
        if entity.kind == "wall":
            drawn = doc.modelspace().add_line(points[0], points[1], dxfattribs=attrs)
        elif entity.kind == "opening":
            drawn = doc.modelspace().add_point(points[0], dxfattribs=attrs)
        else:
            drawn = doc.modelspace().add_lwpolyline(
                points, close=entity.kind in ("room", "boundary", "fixture"), dxfattribs=attrs
            )
        metadata = json.dumps(entity.metadata, ensure_ascii=True, separators=(",", ":"))
        drawn.set_xdata(APP, [(1000, metadata[i : i + 200]) for i in range(0, len(metadata), 200)])


def import_dxf(path: Path, project: ProjectContext | None = None) -> BuildingModel:
    doc = ezdxf.readfile(path)
    if not doc.units:
        raise ValueError("DXF $INSUNITS is missing; declare drawing units before import")
    factor = units.conversion_factor(InsertUnits(doc.units), InsertUnits.Millimeters)
    entities = []
    for drawn in doc.modelspace():
        kind = next((key for key, value in LAYERS.items() if value == drawn.dxf.layer), None)
        if kind is None:
            continue
        if not drawn.has_xdata(APP):
            raise ValueError(f"{drawn.dxf.layer} is missing exact-CAD metadata")
        if isinstance(drawn, Line):
            points = [(drawn.dxf.start.x, drawn.dxf.start.y), (drawn.dxf.end.x, drawn.dxf.end.y)]
        elif isinstance(drawn, Point):
            points = [(drawn.dxf.location.x, drawn.dxf.location.y)]
        elif isinstance(drawn, LWPolyline):
            if any(abs(p[4]) > 0 for p in drawn.get_points()):
                raise ValueError("curved/bulged exact polylines are unsupported")
            if kind in ("room", "boundary", "fixture") and not drawn.closed:
                raise ValueError("room/fixture polygons must be closed")
            points = [(p[0], p[1]) for p in drawn.get_points()]
        else:
            raise ValueError(f"unsupported exact entity: {drawn.dxftype()}")
        data = json.loads("".join(str(tag.value) for tag in drawn.get_xdata(APP)))
        entities.append(
            CadEntity(
                kind=kind, points=[(x * factor, y * factor) for x, y in points], metadata=data
            )
        )
    model = entities_model(entities, project)
    labels: dict[str, list[str]] = {}
    layer = load_config("dxf_layers")["room_label"]
    for text in doc.modelspace().query("TEXT"):
        if not isinstance(text, Text):
            continue
        if text.dxf.layer != layer:
            continue
        position = text.dxf.align_point if text.dxf.halign or text.dxf.valign else text.dxf.insert
        point = ShapePoint(position.x * factor, position.y * factor)
        contained = [r.id for r in model.rooms if Polygon(r.clear_polygon).covers(point)]
        if len(contained) == 1:
            labels.setdefault(contained[0], []).append(text.dxf.text)
    rooms = [
        r.model_copy(update={"label": labels[r.id][0]}) if len(labels.get(r.id, [])) == 1 else r
        for r in model.rooms
    ]
    location = extract_dxf_location(path, doc)
    return model.model_copy(
        update={
            "rooms": rooms,
            "location_extraction": location,
            "warnings": [
                f"Candidate site address (unconfirmed): {item.value}"
                for item in location.candidates
                if item.field == "address"
            ],
        }
    )
