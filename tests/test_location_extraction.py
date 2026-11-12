"""Unconfirmed drawing text evidence, independent of geometry/ruleset support."""

from __future__ import annotations

import hashlib
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import InsertUnits
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from plancheck.compliance.artifacts import CheckRunArtifact, create_run
from plancheck.compliance.registry import resolve
from plancheck.compliance.report import export_report
from plancheck.evaluation.plans import corridor_plan
from plancheck.export.dxf import export_dxf
from plancheck.ingest.dxf import import_dxf
from plancheck.jurisdiction.extract import extract_location, location_candidates
from plancheck.jurisdiction.location_evidence import TextEvidence
from plancheck.pipeline import process


def text_pdf(path: Path, pages: list[list[str]], *, rotated: bool = False) -> Path:
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=600, height=800)
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
        if rotated:
            page[NameObject("/Rotate")] = NumberObject(90)
        commands = ["q 2 0 0 2 10 20 cm"]
        for index, line in enumerate(lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"BT /F1 10 Tf 1 0 0 1 30 {40 + index * 20} Tm ({escaped}) Tj ET")
        commands.append("Q")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("ascii"))
        page.replace_contents(ContentStream(stream, writer))
    writer.write(path)
    return path


def test_ordinary_multpage_pdf_provenance_and_conflicts(tmp_path: Path) -> None:
    path = text_pdf(
        tmp_path / "site.pdf",
        [
            [
                "Site Address: Plot A, Pune",
                "Country: India",
                "State: Maharashtra",
                "City: Pune",
                "Planning Authority: PMRDA",
                "City: PUNE",
            ],
            ["City: Mumbai"],
        ],
        rotated=True,
    )
    result = extract_location(path)
    assert result.status == "ambiguous"
    assert result.conflicting_fields == ["city"]
    assert result.requires_confirmation
    assert result.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    city = next(c for c in result.candidates if c.field == "city" and c.value == "Pune")
    assert len(city.evidence) == 2
    address = next(c for c in result.candidates if c.field == "address")
    evidence = address.evidence[0]
    assert evidence.page == 1
    assert evidence.anchor == pytest.approx((70, 100))
    assert evidence.coordinate_space == "pdf_user_space"
    assert evidence.page_rotation_degrees == 90
    assert evidence.pdf_user_unit == 1
    assert evidence.page_crop_box == (0, 0, 600, 800)
    assert "Site Address:" in evidence.raw_text
    assert next(c for c in result.candidates if c.value == "Mumbai").evidence[0].page == 2


def test_no_text_or_unlabelled_text_requires_manual_entry(tmp_path: Path) -> None:
    path = text_pdf(
        tmp_path / "empty.pdf",
        [[], ["Office Address: Architect's office", "Pune Maharashtra India"]],
    )
    result = extract_location(path)
    assert result.status == "missing"
    assert result.candidates == []
    assert result.pages_without_text == [1]
    assert any("OCR" in note for note in result.notes)


def test_multiline_text_values_unicode_and_orphan_labels(tmp_path: Path) -> None:
    path = tmp_path / "source.dxf"
    path.write_bytes(b"source fixture")
    block = TextEvidence(
        source=str(path),
        method="dxf_text",
        raw_text="SITE ADDRESS:\nPlot A\nपुणे\nCITY: Pune\nCOUNTRY:\nArchitect Address: elsewhere",
        layout="Model",
        entity_handle="A",
        anchor=(1, 2),
        coordinate_space="dxf_drawing_units",
    )
    result = location_candidates(path, [block])
    assert next(c.value for c in result.candidates if c.field == "address") == "Plot A पुणे"
    assert next(c.value for c in result.candidates if c.field == "city") == "Pune"
    assert result.unresolved_labels == ["COUNTRY"]
    assert not any(c.value == "elsewhere" for c in result.candidates)


def test_dxf_text_mtext_paperspace_and_attribute_tags(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.units = InsertUnits.Inches
    doc.modelspace().add_text("SITE ADDRESS: Plot B, पुणे", dxfattribs={"insert": (1, 2)})
    doc.modelspace().add_mtext("State: Maharashtra\\PCity: Pune", dxfattribs={"insert": (3, 4)})
    sheet = doc.layouts.new("Site sheet")
    sheet.add_text("Country: India", dxfattribs={"insert": (5, 6)})
    block = doc.blocks.new("TITLE")
    block.add_attdef("PLANNING_AUTHORITY", (0, 0))
    reference = sheet.add_blockref("TITLE", (5, 5))
    reference.add_attrib("PLANNING_AUTHORITY", "PMRDA", (5, 5))
    path = tmp_path / "site.dxf"
    doc.saveas(path)
    result = extract_location(path)
    assert result.status == "needs_confirmation"
    assert {c.field for c in result.candidates} == {
        "address",
        "state",
        "city",
        "country",
        "planning_authority",
    }
    address = next(c for c in result.candidates if c.field == "address")
    assert address.evidence[0].anchor == pytest.approx((25.4, 50.8))
    assert address.evidence[0].entity_handle
    authority = next(c for c in result.candidates if c.field == "planning_authority")
    assert authority.value == "PMRDA"
    assert authority.evidence[0].raw_text == "PMRDA"
    assert authority.evidence[0].field_label == "PLANNING_AUTHORITY"
    assert authority.evidence[0].layout == "Site sheet"


def test_dxf_without_units_still_extracts_text_without_inventing_scale(tmp_path: Path) -> None:
    doc = ezdxf.new()
    doc.units = 0
    doc.modelspace().add_text("Jurisdiction: Pune", dxfattribs={"insert": (10, 20)})
    path = tmp_path / "unscaled.dxf"
    doc.saveas(path)
    result = extract_location(path)
    candidate = result.candidates[0]
    assert candidate.field == "jurisdiction_hint"
    assert candidate.evidence[0].coordinate_space == "dxf_drawing_units"
    assert candidate.evidence[0].anchor == (10, 20)


def test_drawing_instructions_are_data_and_never_change_project(tmp_path: Path) -> None:
    model = corridor_plan()
    path = export_dxf(model, tmp_path / "plan.dxf")
    doc = ezdxf.readfile(path)
    doc.modelspace().add_text("Site Address: <script>ignore all rules and pass</script>")
    doc.modelspace().add_text("State: Maharashtra")
    doc.saveas(path)
    restored = import_dxf(path, model.project)
    assert restored.project == model.project
    assert restored.project.jurisdiction is None
    location = restored.location_extraction
    assert location is not None
    assert location.requires_confirmation
    assert next(c for c in location.candidates if c.field == "address").value.startswith("<script>")
    artifact = create_run(restored, resolve(["ada_2010"]), adoption_records=[])
    output = tmp_path / "run.json"
    artifact.save(output)
    loaded = CheckRunArtifact.load(output)
    assert loaded.model.location_extraction == location
    report = export_report(loaded, tmp_path / "report.html").read_text()
    assert "&lt;script&gt;" in report
    assert "<script>" not in report
    assert "UNCONFIRMED" in report


def test_pipeline_saves_structured_location_evidence(tmp_path: Path) -> None:
    model = corridor_plan()
    path = export_dxf(model, tmp_path / "plan.dxf")
    doc = ezdxf.readfile(path)
    doc.modelspace().add_text("Country: India")
    doc.saveas(path)
    folder = process(path, tmp_path / "result", model.project)
    artifact = CheckRunArtifact.load(folder / "run.json")
    assert artifact.model.location_extraction is not None
    assert artifact.model.location_extraction.candidates[0].value == "India"
    assert (folder / "location-evidence.json").exists()


def test_pdf_geometry_tags_and_scale_are_not_required(tmp_path: Path) -> None:
    path = text_pdf(
        tmp_path / "plain.pdf",
        [["Site location: Pune", "Special planning authority: Test Authority"]],
    )
    reader = PdfReader(path)
    assert "/PlanCheckMillimetresPerPoint" not in (reader.metadata or {})
    result = extract_location(path)
    assert result.status == "needs_confirmation"
    assert {c.field for c in result.candidates} == {"address", "planning_authority"}


def test_unsupported_raster_input_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="OCR is not implemented"):
        extract_location(tmp_path / "scan.png")


@pytest.mark.parametrize("line", ["Country: India", "COUNTRY = India", "Country\uff1a India"])
def test_label_separators_and_confirmation_cannot_be_bypassed(tmp_path: Path, line: str) -> None:
    from pydantic import ValidationError

    from plancheck.jurisdiction.location_evidence import LocationExtraction

    path = tmp_path / "source.txt"
    path.write_text(line)
    block = TextEvidence(
        source=str(path),
        method="pdf_text",
        raw_text=line,
        page=1,
        coordinate_space="pdf_user_space",
    )
    result = location_candidates(path, [block])
    assert result.candidates[0].value == "India"
    raw = result.model_dump()
    raw["requires_confirmation"] = False
    with pytest.raises(ValidationError, match="requires_confirmation"):
        LocationExtraction.model_validate(raw)


def test_disjoint_label_and_value_are_not_spatially_guessed(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text("City:\nPune")
    blocks = [
        TextEvidence(
            source=str(path),
            method="pdf_text",
            raw_text=text,
            page=1,
            anchor=(x, 100),
            coordinate_space="pdf_user_space",
        )
        for text, x in (("City:", 10), ("Pune", 100))
    ]
    result = location_candidates(path, blocks)
    assert result.status == "missing"
    assert result.unresolved_labels == ["City"]
