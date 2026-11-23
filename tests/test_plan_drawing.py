"""The plan drawing with findings (D2): the SVG, the HTML report and the page route."""

from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from plancheck import web
from plancheck.compliance.artifacts import CheckRunArtifact, create_run
from plancheck.compliance.engine import Report, run
from plancheck.compliance.registry import resolve
from plancheck.compliance.report import export_report, measurement_text, requirement_text
from plancheck.compliance.verdict import Verdict
from plancheck.evaluation.plans import corridor_plan, sample_office_plan, transform_model
from plancheck.evaluation.validate import signatures
from plancheck.export.dxf import export_dxf
from plancheck.export.svg import finding_shapes, plan_svg
from plancheck.ingest.vector_pdf import export_vector_pdf
from plancheck.model.types import BuildingModel
from plancheck.pipeline import process

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture(scope="module")
def office() -> tuple[BuildingModel, Report]:
    model = sample_office_plan()
    return model, run(model, resolve(["ada_2010"]))


def finding_groups(svg: str) -> dict[int, ET.Element]:
    root = ET.fromstring(svg)
    return {
        int(group.attrib["data-finding"]): group
        for group in root.iter(f"{SVG}g")
        if "pc-finding" in group.attrib.get("class", "").split()
    }


def test_sample_office_plan_has_each_kind_of_result(office: tuple[BuildingModel, Report]) -> None:
    model, report = office
    assert len(model.rooms) == 7
    by_element = {
        (finding.rule_id, finding.element_ids[0]): finding.verdict for finding in report.findings
    }
    assert by_element[("ada2010.door-clear-width", "D04")] == Verdict.FAIL
    assert by_element[("ada2010.door-clear-width", "D01")] == Verdict.BORDERLINE
    assert by_element[("ada2010.door-clear-width", "D08")] == Verdict.PASS
    assert by_element[("ada2010.door-maneuvering-clearance", "D08")] == Verdict.FAIL
    # The office is reached only through the borderline door, so its route is borderline too.
    assert by_element[("ada2010.accessible-route", "R07")] == Verdict.BORDERLINE


def test_svg_has_one_group_for_every_finding_that_can_be_drawn(
    office: tuple[BuildingModel, Report],
) -> None:
    model, report = office
    groups = finding_groups(plan_svg(model, report))
    expected = {
        number
        for number, finding in enumerate(report.findings, start=1)
        if finding_shapes(model, finding)
    }
    assert set(groups) == expected
    assert len(expected) == len(report.findings)  # every finding here names an element
    for number, finding in enumerate(report.findings, start=1):
        group = groups[number]
        assert f"v-{finding.verdict}" in group.attrib["class"]
        assert group.attrib["id"] == f"pc-f{number}"
        # Only findings that report a problem carry a numbered badge linking to their row.
        links = [a.attrib["href"] for a in group.iter(f"{SVG}a")]
        problem = finding.verdict in (Verdict.FAIL, Verdict.BORDERLINE)
        assert links == ([f"#pc-row-{number}"] if problem else [])


def test_finding_without_evidence_is_drawn_as_its_element(
    office: tuple[BuildingModel, Report],
) -> None:
    model, report = office
    number, route = next(
        (n, f)
        for n, f in enumerate(report.findings, start=1)
        if f.rule_id == "ada2010.accessible-route" and f.element_ids == ["R07"]
    )
    shapes = finding_shapes(model, route)
    assert [shape.kind for shape in shapes] == ["polygon"]
    assert shapes[0].points == model.room("R07").clear_polygon
    assert "pc-fallback" in finding_groups(plan_svg(model, report))[number].attrib["class"]


def test_plan_without_a_report_draws_no_findings() -> None:
    svg = plan_svg(corridor_plan())
    assert finding_groups(svg) == {}
    assert ET.fromstring(svg).attrib["aria-label"] == "Floor plan"


def test_drawing_text_is_escaped() -> None:
    model = corridor_plan()
    room = model.rooms[0].model_copy(update={"label": "<script>alert(1)</script>"})
    model = model.model_copy(update={"rooms": [room]})
    svg = plan_svg(model, run(model, resolve(["ada_2010"])))
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    labels = [text.text for text in ET.fromstring(svg).iter(f"{SVG}text")]
    assert "<script>alert(1)</script>" in labels


def test_rotating_the_model_rotates_the_drawing(office: tuple[BuildingModel, Report]) -> None:
    model, report = office
    rotated = transform_model(model, angle=90, dx=5000, dy=-2000)
    rotated_report = run(rotated, resolve(["ada_2010"]))
    assert signatures(rotated_report) == signatures(report)
    before = [float(v) for v in ET.fromstring(plan_svg(model, report)).attrib["viewBox"].split()]
    after = [
        float(v) for v in ET.fromstring(plan_svg(rotated, rotated_report)).attrib["viewBox"].split()
    ]
    # A quarter turn swaps the width and height of the drawing, wherever the model sits.
    # The margin follows the larger side, so it is unchanged.
    assert after[2] == pytest.approx(before[3], abs=0.2)
    assert after[3] == pytest.approx(before[2], abs=0.2)
    assert len(finding_groups(plan_svg(rotated, rotated_report))) == len(report.findings)


def test_html_report_draws_the_plan_and_lists_problems_first(tmp_path: Path) -> None:
    artifact = create_run(sample_office_plan(), resolve(["ada_2010"]), adoption_records=[])
    text = export_report(artifact, tmp_path / "report.html").read_text()
    assert text.startswith("<!doctype html>")
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in text
    assert "<pre>" in text  # the complete text record is kept
    rows = [line.split('"')[0] for line in text.split('<tr id="pc-row-')[1:]]
    report = artifact.report
    shown = [n for n in map(int, rows) if report.findings[n - 1].verdict != "not_applicable"]
    verdicts = [str(report.findings[n - 1].verdict) for n in shown]
    order = ["fail", "borderline", "unknown", "pass"]
    assert verdicts == sorted(verdicts, key=order.index)
    assert verdicts[0] == "fail"
    assert len(rows) == len(report.findings)
    # A verdict is marked with a symbol and a word, not with colour alone.
    assert "✕ Fail" in text
    assert "! Borderline" in text
    door = next(f for f in report.findings if f.element_ids == ["D04"] and f.measured)
    assert measurement_text(door) == "710 mm (27.95 in) ± 0 mm"
    assert requirement_text(door) == "32 in (812.8 mm)"
    assert measurement_text(door) in text


def test_pipeline_writes_the_drawing_and_both_paths_draw_the_same_findings(
    tmp_path: Path,
) -> None:
    model = sample_office_plan()
    drawn = {}
    for kind, export in (("dxf", export_dxf), ("pdf", export_vector_pdf)):
        source = export(model, tmp_path / f"source.{kind}")
        output = process(source, tmp_path / kind, model.project)
        report = CheckRunArtifact.load(output / "run.json").report
        groups = finding_groups((output / "plan.svg").read_text(encoding="utf-8"))
        drawn[kind] = {n: g.attrib["data-verdict"] for n, g in groups.items()}
        assert len(groups) == len(report.findings)
    assert drawn["dxf"] == drawn["pdf"]


def test_page_route_ignores_its_query_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "STORE", tmp_path)
    server = web.LocalServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/?project=00000000-0000-0000-0000-000000000000")
        response = connection.getresponse()
        assert response.status == 200
        assert b"<title>PlanCheck" in response.read()
        connection.request("GET", "/api/projects?x=1")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()
