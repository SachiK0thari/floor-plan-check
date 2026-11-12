"""BCF 2.1 XML issue archives with GUIDs checked against the actual IFC file."""

from __future__ import annotations

import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import ifcopenshell

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.compliance.report import DISCLAIMER, finding_description
from plancheck.compliance.verdict import Verdict
from plancheck.export.ifc import ifc_guid


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _vector(parent: ET.Element, name: str, values: tuple[float, float, float]) -> None:
    node = ET.SubElement(parent, name)
    for key, value in zip(("X", "Y", "Z"), values, strict=True):
        ET.SubElement(node, key).text = f"{value:.12g}"


def export_bcf(
    artifact: CheckRunArtifact, path: Path, ifc_path: Path, project_id: str = "plancheck"
) -> Path:
    model = artifact.model
    file = ifcopenshell.open(str(ifc_path))
    guids = {str(e.GlobalId) for e in file.by_type("IfcRoot")}
    project_guid = ifc_guid(project_id, "project")
    if project_guid not in guids:
        raise ValueError("IFC project identity does not match the requested project_id")
    mapping = {w.id: ifc_guid(project_id, f"wall:{w.id}") for w in model.walls}
    mapping.update({r.id: ifc_guid(project_id, f"space:{r.id}") for r in model.rooms})
    mapping.update(
        {
            o.id: ifc_guid(project_id, f"{'void' if o.kind == 'opening' else 'opening'}:{o.id}")
            for o in model.openings
        }
    )
    issues = [
        f
        for f in artifact.report.findings + artifact.report.group_findings
        if f.verdict in (Verdict.FAIL, Verdict.UNKNOWN, Verdict.BORDERLINE)
    ]
    # Validate before opening the output: no dangling or invented component IDs.
    for finding in issues:
        for element_id in finding.element_ids:
            if element_id not in mapping or mapping[element_id] not in guids:
                raise ValueError(f"BCF element {element_id} has no corresponding IFC GlobalId")
    points = [p for w in model.walls for p in (w.start, w.end)]
    points += [p for r in model.rooms for p in r.clear_polygon]
    minx = min((p[0] for p in points), default=0)
    maxx = max((p[0] for p in points), default=1000)
    miny = min((p[1] for p in points), default=0)
    maxy = max((p[1] for p in points), default=1000)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("bcf.version", _xml(ET.Element("Version", VersionId="2.1")))
        for index, finding in enumerate(issues):
            identity = (
                f"{project_guid}/{finding.rule_id}/{finding.element_ids}/{finding.group}/{index}"
            )
            topic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
            view_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity + "/view"))
            markup = ET.Element("Markup")
            header = ET.SubElement(markup, "Header")
            source = ET.SubElement(header, "File", IfcProject=project_guid, isExternal="true")
            ET.SubElement(source, "Filename").text = ifc_path.name
            topic = ET.SubElement(
                markup, "Topic", Guid=topic_id, TopicType="Issue", TopicStatus="Open"
            )
            if finding.citation and finding.citation.source_url:
                ET.SubElement(topic, "ReferenceLink").text = finding.citation.source_url
            ET.SubElement(topic, "Title").text = f"{finding.verdict}: {finding.title}"
            ET.SubElement(topic, "CreationDate").text = artifact.created_at.isoformat()
            ET.SubElement(topic, "CreationAuthor").text = "PlanCheck"
            ET.SubElement(topic, "Description").text = (
                finding_description(finding) + "\n\n" + DISCLAIMER
            )
            viewpoint = ET.SubElement(markup, "Viewpoints", Guid=view_id)
            ET.SubElement(viewpoint, "Viewpoint").text = "viewpoint.bcfv"
            visual = ET.Element("VisualizationInfo", Guid=view_id)
            components = ET.SubElement(visual, "Components")
            ET.SubElement(
                components, "ViewSetupHints", SpacesVisible="true", OpeningsVisible="true"
            )
            if finding.element_ids:
                selected = ET.SubElement(components, "Selection")
                for element_id in finding.element_ids:
                    ET.SubElement(selected, "Component", IfcGuid=mapping[element_id])
            ET.SubElement(components, "Visibility", DefaultVisibility="true")
            camera = ET.SubElement(visual, "OrthogonalCamera")
            _vector(camera, "CameraViewPoint", ((minx + maxx) / 2000, (miny + maxy) / 2000, 20.0))
            _vector(camera, "CameraDirection", (0.0, 0.0, -1.0))
            _vector(camera, "CameraUpVector", (0.0, 1.0, 0.0))
            ET.SubElement(camera, "ViewToWorldScale").text = str(
                max(maxx - minx, maxy - miny, 1000) * 1.2 / 1000
            )
            archive.writestr(f"{topic_id}/markup.bcf", _xml(markup))
            archive.writestr(f"{topic_id}/viewpoint.bcfv", _xml(visual))
    return path
