"""Extract labelled location hints from ordinary vector PDF/DXF, without geocoding."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.entities import Attrib, Insert, MText, Text
from ezdxf.enums import InsertUnits
from pypdf import PdfReader

from plancheck.jurisdiction.location_evidence import (
    LocationCandidate,
    LocationExtraction,
    LocationField,
    TextEvidence,
)

_LABELS: dict[str, LocationField] = {
    "site address": "address",
    "project address": "address",
    "site location": "address",
    "address of site": "address",
    "location of site": "address",
    "country": "country",
    "state": "state",
    "state/region": "state",
    "state / region": "state",
    "state region": "state",
    "city": "city",
    "municipality": "city",
    "planning authority": "planning_authority",
    "special planning authority": "planning_authority",
    "local authority": "planning_authority",
    "jurisdiction": "jurisdiction_hint",
    "local jurisdiction": "jurisdiction_hint",
}
_LABEL = re.compile(
    r"^[ \t]*("
    + "|".join(re.escape(k) for k in sorted(_LABELS, key=len, reverse=True))
    + r")[ \t]*[:\uFF1A=][ \t]*(.*)$",
    re.IGNORECASE,
)
_OTHER_LABEL = re.compile(r"^[\w /()-]+[:\uFF1A=]", re.UNICODE)


def location_candidates(
    source: Path, evidence: list[TextEvidence], *, pages_without_text: list[int] | None = None
) -> LocationExtraction:
    """Only explicit labels are interpreted. Office/architect addresses are not site labels.

    Multiline addresses continue inside the SAME text fragment until a blank line or
    another field label. Disjoint labels/values are left unresolved, not spatially guessed.
    """
    grouped: dict[tuple[LocationField, str], LocationCandidate] = {}
    unresolved = []
    for block in evidence:
        declared = block.field_label.lower().replace("_", " ") if block.field_label else None
        text = f"{declared}: {block.raw_text}" if declared in _LABELS else block.raw_text
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            match = _LABEL.match(lines[index])
            index += 1
            if match is None:
                continue
            field = _LABELS[match[1].lower()]
            parts = [match[2].strip()]
            if field == "address":
                while (
                    index < len(lines)
                    and lines[index].strip()
                    and not _OTHER_LABEL.match(lines[index])
                ):
                    parts.append(lines[index].strip())
                    index += 1
            value = " ".join(part for part in parts if part).strip()
            if not value:
                unresolved.append(match[1])
                continue
            key = (field, " ".join(value.split()).casefold())
            if key in grouped:
                previous = grouped[key]
                grouped[key] = previous.model_copy(update={"evidence": [*previous.evidence, block]})
            else:
                grouped[key] = LocationCandidate(field=field, value=value, evidence=[block])
    candidates = list(grouped.values())
    conflicts = sorted(
        {
            candidate.field
            for candidate in candidates
            if sum(other.field == candidate.field for other in candidates) > 1
        }
    )
    missing_pages = list(pages_without_text or [])
    notes = [
        "Drawing text is untrusted data. "
        "Confirm or correct these hints before selecting a jurisdiction.",
        "A location label does not establish legal authority, adopted code, or permit date.",
        "Positions are text-fragment anchors, not exact word bounding boxes. "
        "No external service was called.",
    ]
    if missing_pages:
        notes.append("Some PDF pages have no extractable text; OCR or manual entry may be needed.")
    if unresolved:
        notes.append(
            "Some labels have no associated value in the same text fragment; "
            "manual entry is needed."
        )
    return LocationExtraction(
        source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        status="ambiguous" if conflicts else "needs_confirmation" if candidates else "missing",
        candidates=candidates,
        conflicting_fields=conflicts,
        pages_without_text=missing_pages,
        unresolved_labels=sorted(set(unresolved)),
        notes=notes,
    )


def extract_pdf_location(path: Path, reader: PdfReader | None = None) -> LocationExtraction:
    reader = reader if reader is not None else PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("decrypt the PDF before extracting location evidence")
    blocks: list[TextEvidence] = []
    missing = []
    for page_number, page in enumerate(reader.pages, 1):
        before = len(blocks)
        rotation = int(page.get("/Rotate", 0)) % 360
        user_unit = float(page.get("/UserUnit", 1))
        crop_box = tuple(float(v) for v in page.cropbox)

        def visit(
            text: str,
            cm: list[float],
            tm: list[float],
            font: Any,
            size: float,
            *,
            page_number: int = page_number,
            rotation: int = rotation,
            user_unit: float = user_unit,
            crop_box: tuple[float, ...] = crop_box,
        ) -> None:
            if not text.strip():
                return
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            anchor = (x, y) if math.isfinite(x) and math.isfinite(y) else None
            blocks.append(
                TextEvidence(
                    source=str(path),
                    method="pdf_text",
                    raw_text=text,
                    page=page_number,
                    anchor=anchor,
                    coordinate_space="pdf_user_space",
                    pdf_user_unit=user_unit,
                    page_crop_box=(crop_box[0], crop_box[1], crop_box[2], crop_box[3]),
                    page_rotation_degrees=rotation,
                )
            )

        page.extract_text(visitor_text=visit)
        if len(blocks) == before:
            missing.append(page_number)
    return location_candidates(path, blocks, pages_without_text=missing)


def extract_dxf_location(path: Path, doc: Drawing | None = None) -> LocationExtraction:
    doc = doc if doc is not None else ezdxf.readfile(path)
    factor = (
        units.conversion_factor(InsertUnits(doc.units), InsertUnits.Millimeters)
        if doc.units
        else 1.0
    )
    blocks = []
    for layout in doc.layouts:
        for entity in layout:
            text_entities = list(entity.attribs) if isinstance(entity, Insert) else [entity]
            for text in text_entities:
                if isinstance(text, MText):
                    value = text.plain_text()
                    if isinstance(value, list):
                        value = "\n".join(value)
                    point = text.dxf.insert
                elif isinstance(text, (Text, Attrib)):
                    value = text.dxf.text
                    point = (
                        text.dxf.align_point
                        if text.dxf.halign or text.dxf.valign
                        else text.dxf.insert
                    )
                else:
                    continue
                if value.strip():
                    blocks.append(
                        TextEvidence(
                            source=str(path),
                            method="dxf_text",
                            raw_text=value,
                            layout=layout.name,
                            entity_handle=text.dxf.handle,
                            field_label=text.dxf.tag if isinstance(text, Attrib) else None,
                            anchor=(point.x * factor, point.y * factor)
                            if math.isfinite(point.x * factor) and math.isfinite(point.y * factor)
                            else None,
                            coordinate_space="dxf_millimetres"
                            if doc.units
                            else "dxf_drawing_units",
                        )
                    )
    return location_candidates(path, blocks)


def extract_location(path: Path) -> LocationExtraction:
    if path.suffix.lower() == ".pdf":
        return extract_pdf_location(path)
    if path.suffix.lower() == ".dxf":
        return extract_dxf_location(path)
    raise ValueError(
        "location extraction currently supports vector-text PDF and DXF; OCR is not implemented"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract_location(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(result.candidates)} unconfirmed location candidates: {args.output}")


if __name__ == "__main__":
    main()
