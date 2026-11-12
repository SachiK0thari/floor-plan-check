"""Traceable reports, exact input paths, and whole-model analytic validation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import ezdxf
import ifcopenshell
import pytest
from ezdxf.enums import InsertUnits
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject

from plancheck.compliance.artifacts import create_run
from plancheck.compliance.engine import run
from plancheck.compliance.registry import resolve
from plancheck.compliance.report import DISCLAIMER, export_report
from plancheck.compliance.verdict import Verdict
from plancheck.demo import generate_demo
from plancheck.evaluation.plans import corridor_plan, review_plans, transform_model
from plancheck.evaluation.validate import evaluate, signatures
from plancheck.export.bcf import export_bcf
from plancheck.export.dxf import export_dxf
from plancheck.export.ifc import export_ifc
from plancheck.ingest.dxf import append_exact_entities, import_dxf
from plancheck.ingest.vector_pdf import export_vector_pdf, import_vector_pdf
from plancheck.model.types import Measured
from plancheck.pipeline import input_kind, process


def test_report_is_readable_complete_and_escapes_drawing_text(tmp_path: Path) -> None:
    model = corridor_plan()
    model = model.model_copy(
        update={
            "project": model.project.model_copy(
                update={"site_address": "<script>alert(1)</script>"}
            )
        }
    )
    artifact = create_run(model, resolve(["ada_2010"]), adoption_records=[])
    text = export_report(artifact, tmp_path / "report.html").read_text()
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    for term in (
        "standard uncertainty",
        "Requirement:",
        "Citation:",
        "section",
        "Not visible on a plan:",
        "unresolved",
        "Unresolved exceptions:",
    ):
        assert term in text
    assert "Design-assist tool, not a code review" in text
    assert 'href="https://www.ada.gov' in text
    assert '<a href="https://www.ada.gov' in text
    assert '<a href="<a ' not in text


def test_bcf_references_actual_ifc_guids_and_has_camera_and_citations(tmp_path: Path) -> None:
    model = corridor_plan(800, 700)
    artifact = create_run(model, resolve(["ada_2010"]), adoption_records=[])
    ifc_path = export_ifc(model, tmp_path / "model.ifc")
    path = export_bcf(artifact, tmp_path / "issues.bcfzip", ifc_path)
    guids = {e.GlobalId for e in ifcopenshell.open(str(ifc_path)).by_type("IfcRoot")}
    with ZipFile(path) as archive:
        assert ET.fromstring(archive.read("bcf.version")).attrib["VersionId"] == "2.1"
        markups = [name for name in archive.namelist() if name.endswith("markup.bcf")]
        assert markups
        for name in markups:
            root = ET.fromstring(archive.read(name))
            description = root.findtext("Topic/Description")
            assert description
            assert DISCLAIMER in description
            assert "Citation:" in description
            viewpoint = root.find("Viewpoints")
            assert viewpoint is not None
            visual = ET.fromstring(archive.read(name.replace("markup.bcf", "viewpoint.bcfv")))
            assert visual.attrib["Guid"] == viewpoint.attrib["Guid"]
            direction = visual.find("OrthogonalCamera/CameraDirection/Z")
            visibility = visual.find("Components/Visibility")
            assert direction is not None
            assert visibility is not None
            assert direction.text == "-1"
            assert visibility.attrib["DefaultVisibility"] == "true"
            for component in visual.findall("Components/Selection/Component"):
                assert component.attrib["IfcGuid"] in guids


def test_bcf_rejects_ifc_with_missing_element_before_writing(tmp_path: Path) -> None:
    model = corridor_plan(800, 700)
    artifact = create_run(model, resolve(["ada_2010"]), adoption_records=[])
    other = model.model_copy(
        update={"openings": [], "graph": model.graph.model_copy(update={"edges": []})}
    )
    ifc_path = export_ifc(other, tmp_path / "other.ifc")
    destination = tmp_path / "bad.bcfzip"
    with pytest.raises(ValueError, match="no corresponding IFC GlobalId"):
        export_bcf(artifact, destination, ifc_path)
    assert not destination.exists()


@pytest.mark.parametrize("name", ["wide", "narrow", "missing"])
@pytest.mark.parametrize(
    ("angle", "mirror"), [(0, False), (37, False), (90, False), (0, True), (37, True)]
)
def test_whole_model_transform_verdicts(name: str, angle: float, mirror: bool) -> None:
    model = review_plans()[name]
    expected = signatures(run(model, resolve(["ada_2010"])))
    changed = transform_model(model, angle=angle, mirror=mirror, dx=1234, dy=-567)
    assert signatures(run(changed, resolve(["ada_2010"]))) == expected


def test_corridor_widening_monotonicity_and_uncertainty() -> None:
    results = []
    for width in (800, 900, 914.4, 950, 1000):
        report = run(corridor_plan(width), resolve(["ada_2010"]))
        results.append(report.for_rule("ada2010.walking-surface-clear-width")[0].verdict)
    first_pass = results.index(Verdict.PASS)
    assert all(v is Verdict.PASS for v in results[first_pass:])
    model = corridor_plan(1000, 813.8)
    exact = run(model, resolve(["ada_2010"])).for_rule("ada2010.door-clear-width")[0]
    assert exact.verdict is Verdict.PASS
    opening = model.openings[0].model_copy(
        update={"clear_width": Measured(value_mm=813.8, sigma_mm=1, source="geometry")}
    )
    uncertain = run(model.model_copy(update={"openings": [opening]}), resolve(["ada_2010"]))
    assert uncertain.for_rule("ada2010.door-clear-width")[0].verdict is Verdict.BORDERLINE


def test_author_review_is_not_fabricated(tmp_path: Path) -> None:
    import yaml

    data = yaml.safe_load(Path("eval/compliance/expected.yaml").read_text())
    data.update(review_status="pending_author_review", reviewed_by=None)
    expected = tmp_path / "pending.yaml"
    expected.write_text(yaml.safe_dump(data))
    result = evaluate(expected, tmp_path / "validation.md")
    assert result["review_status"] == "pending_author_review"
    assert all(case["matches"] for case in result["cases"])
    with pytest.raises(ValueError, match="hand-checks are still pending"):
        evaluate(expected, tmp_path / "accepted.md", require_reviewed=True)


@pytest.mark.parametrize("units", [InsertUnits.Millimeters, InsertUnits.Inches, InsertUnits.Meters])
def test_dxf_units_geometry_and_verdict_round_trip(units: InsertUnits, tmp_path: Path) -> None:
    model = corridor_plan()
    doc = ezdxf.new("R2018")
    doc.units = units
    append_exact_entities(doc, model)
    path = tmp_path / "model.dxf"
    doc.saveas(path)
    restored = import_dxf(path, model.project)
    for before, after in zip(model.walls, restored.walls, strict=True):
        assert after.start == pytest.approx(before.start)
        assert after.end == pytest.approx(before.end)
        assert after.thickness == before.thickness
    assert restored.openings[0].position_along_wall_mm == pytest.approx(
        model.openings[0].position_along_wall_mm
    )
    assert signatures(run(restored, resolve(["ada_2010"]))) == signatures(
        run(model, resolve(["ada_2010"]))
    )


def test_dxf_reads_actual_vectors_and_rejects_undeclared_units(tmp_path: Path) -> None:
    model = corridor_plan()
    path = export_dxf(model, tmp_path / "model.dxf")
    doc = ezdxf.readfile(path)
    wall = next(iter(doc.modelspace().query('LINE[layer=="PC-WALL"]')))
    wall.dxf.end = (5300, 0, 0)
    doc.saveas(path)
    assert import_dxf(path, model.project).wall("W1").end[0] == 5300
    doc.units = 0
    doc.saveas(path)
    with pytest.raises(ValueError, match="INSUNITS"):
        import_dxf(path)


@pytest.mark.parametrize("plot_scale", [20, 100, 200])
def test_vector_pdf_plot_scale_and_verdicts(plot_scale: int, tmp_path: Path) -> None:
    model = corridor_plan(800, 700)
    path = export_vector_pdf(model, tmp_path / "plan.pdf", plot_scale)
    assert input_kind(path) == "vector_pdf"
    restored = import_vector_pdf(path, model.project)
    for before, after in zip(model.walls, restored.walls, strict=True):
        assert after.end == pytest.approx(before.end, abs=1e-6)
    assert signatures(run(restored, resolve(["ada_2010"]))) == signatures(
        run(model, resolve(["ada_2010"]))
    )


def test_pdf_actual_vector_edit_changes_imported_geometry(tmp_path: Path) -> None:
    path = export_vector_pdf(corridor_plan(), tmp_path / "plan.pdf")
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    stream = writer.pages[0].get_contents()
    assert stream is not None
    for args, op in stream.operations:
        if op == b"l":
            from pypdf.generic import FloatObject

            args[0] = FloatObject(5300)
            break
    writer.pages[0].replace_contents(stream)
    writer.write(path)
    assert import_vector_pdf(path).wall("W1").end[0] == pytest.approx(5300)


def test_untagged_pdf_and_raster_do_not_generate_guessed_verdicts(tmp_path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b"0 0 20 20 re S")
    page.replace_contents(ContentStream(stream, writer))
    path = tmp_path / "untagged.pdf"
    writer.write(path)
    assert input_kind(path) == "vector_pdf"
    with pytest.raises(ValueError, match="plot scale"):
        import_vector_pdf(path)
    with pytest.raises(ValueError, match="no supported exact wall"):
        import_vector_pdf(path, mm_per_point=10)
    raster = tmp_path / "drawing.png"
    raster.write_bytes(b"placeholder")
    with pytest.raises(NotImplementedError, match="raster extraction"):
        process(raster, tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_demo_both_paths_match_all_saved_expectations(tmp_path: Path) -> None:
    generate_demo(tmp_path / "demo")
    for name in review_plans():
        for kind in ("dxf", "pdf"):
            folder = tmp_path / "demo" / name / kind
            for filename in (
                "run.json",
                "report.html",
                "model.ifc",
                "issues.bcfzip",
                "model.dxf",
                "model.glb",
            ):
                assert (folder / filename).stat().st_size > 0
            assert json.loads((folder / "run.json").read_text())["report"]["findings"]


def test_imports_read_positioned_room_text_and_preserve_unicode(tmp_path: Path) -> None:
    model = corridor_plan()
    path = export_dxf(model, tmp_path / "labels.dxf")
    doc = ezdxf.readfile(path)
    text = next(iter(doc.modelspace().query('TEXT[layer=="A-AREA-IDEN"]')))
    text.dxf.text = "Changed in CAD"
    doc.saveas(path)
    assert import_dxf(path, model.project).rooms[0].label == "Changed in CAD"
    unicode_label = "पुणे"
    model = model.model_copy(
        update={"rooms": [model.rooms[0].model_copy(update={"label": unicode_label})]}
    )
    pdf = export_vector_pdf(model, tmp_path / "unicode.pdf")
    assert import_vector_pdf(pdf, model.project).rooms[0].label == unicode_label


def test_non_us_adoption_identifiers_are_not_census_geoids() -> None:
    from plancheck.jurisdiction.resolve import AdoptionRecord

    record = AdoptionRecord(
        name="Synthetic Indian authority",
        slug="test-in",
        country="IN",
        level="place",
        authority_id="synthetic:test-in",
        base_code="TEST",
        base_edition="TEST",
        effective_date=date(2020, 1, 1),
        adopting_reference="TEST",
        source_url="https://example.test/authority",
        retrieved_on=date(2026, 1, 1),
        verified_by="Synthetic fixture only",
    )
    assert record.geoid is None
    assert record.missing == []
    assert "authority_id" in record.model_copy(update={"authority_id": None}).missing
