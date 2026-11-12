"""Typed, single-user project persistence for the local exact-input web demo."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.compliance.engine import Report
from plancheck.jurisdiction.extract import extract_location
from plancheck.jurisdiction.location_evidence import LocationExtraction
from plancheck.jurisdiction.proposal import ProjectSettings, availability
from plancheck.jurisdiction.resolve import load_adoption_records
from plancheck.model.types import ProjectContext
from plancheck.pipeline import process

DOWNLOADS = {
    "report.html": "text/html; charset=utf-8",
    "report.md": "text/markdown; charset=utf-8",
    "run.json": "application/json",
    "model.ifc": "application/octet-stream",
    "model.dxf": "application/dxf",
    "model.glb": "model/gltf-binary",
    "issues.bcfzip": "application/zip",
}


class Drawing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{64}\.(pdf|dxf)$")
    name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: LocationExtraction


class RunResult(BaseModel):
    id: UUID
    revision: int
    source_sha256: str
    report: Report


class LocalProject(BaseModel):
    id: UUID
    name: str
    settings: ProjectSettings
    evidence: LocationExtraction | None = None
    drawing: Drawing | None = None
    revision: int = 0
    check_results: RunResult | None = None
    requires_new_run: bool = True
    status: Literal["draft", "ready", "processing", "complete", "error"] = "draft"
    error: str | None = None
    # Kept for compatibility with the first local confirmation flow.
    availability: dict[str, object] = Field(default_factory=dict)


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID | None = None
    name: str = Field(default="Untitled plan", max_length=200)
    settings: ProjectSettings
    upload_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}\.(pdf|dxf)$")
    evidence: LocationExtraction | None = None


class LocalProjects:
    def __init__(self, folder: Path):
        self.folder = folder

    def _write(self, project: LocalProject) -> LocalProject:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{project.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return project

    def get(self, project_id: UUID) -> LocalProject:
        return LocalProject.model_validate_json(
            (self.folder / f"{project_id}.json").read_text(encoding="utf-8")
        )

    def list(self) -> list[LocalProject]:
        return [self.get(UUID(p.stem)) for p in sorted(self.folder.glob("*.json"))]

    def upload(self, name: str, data: bytes) -> Drawing:
        suffix = Path(name).suffix.lower()
        if suffix not in {".pdf", ".dxf"}:
            raise ValueError("Use a vector PDF or DXF. OCR remains pending.")
        digest = hashlib.sha256(data).hexdigest()
        upload_id = digest + suffix
        folder = self.folder / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / upload_id
        path.write_bytes(data)
        extraction = extract_location(path)
        source = Path(name).name
        extraction = extraction.model_copy(
            update={
                "source": source,
                "candidates": [
                    candidate.model_copy(
                        update={
                            "evidence": [
                                item.model_copy(update={"source": source})
                                for item in candidate.evidence
                            ]
                        }
                    )
                    for candidate in extraction.candidates
                ],
            }
        )
        drawing = Drawing(id=upload_id, name=source, sha256=digest, evidence=extraction)
        (folder / f"{upload_id}.json").write_text(drawing.model_dump_json(), encoding="utf-8")
        return drawing

    def save(self, request: SaveRequest) -> LocalProject:
        if request.settings.confirmed and not request.settings.complete:
            raise ValueError("Complete required location fields before confirming")
        previous = self.get(request.id) if request.id else None
        drawing = previous.drawing if previous else None
        if request.upload_id:
            drawing = Drawing.model_validate_json(
                (self.folder / "uploads" / f"{request.upload_id}.json").read_text(encoding="utf-8")
            )
        evidence = drawing.evidence if drawing else request.evidence
        changed = previous is None or (
            previous.settings != request.settings
            or previous.drawing != drawing
            or previous.evidence != evidence
        )
        project = LocalProject(
            id=previous.id if previous else uuid4(),
            name=request.name,
            settings=request.settings,
            evidence=evidence,
            drawing=drawing,
            revision=(previous.revision if previous else 0) + int(changed),
            check_results=previous.check_results if previous and not changed else None,
            requires_new_run=changed or (previous.requires_new_run if previous else True),
            status=(
                previous.status
                if previous and not changed
                else "ready"
                if request.settings.confirmed and drawing
                else "draft"
            ),
            error=previous.error if previous and not changed else None,
            availability=availability(request.settings, load_adoption_records()),
        )
        return self._write(project)

    def run(self, project_id: UUID, revision: int) -> LocalProject:
        project = self.get(project_id)
        settings = project.settings
        if revision != project.revision:
            raise ValueError("Project changed. Reopen the latest saved revision before running.")
        if not settings.confirmed or not settings.complete:
            raise ValueError("Save and confirm the project location before running.")
        if not settings.ada_reference:
            raise ValueError("Explicitly select ADA reference comparison before running.")
        if project.drawing is None:
            raise ValueError("Upload and save a supported drawing before running.")
        project.check_results = None
        project.requires_new_run = True
        project.status = "processing"
        project.error = None
        self._write(project)
        run_id = uuid4()
        output = self.folder / str(project.id) / "runs" / str(run_id)
        try:
            drawing = project.drawing
            source = self.folder / "uploads" / drawing.id
            if hashlib.sha256(source.read_bytes()).hexdigest() != drawing.sha256:
                raise ValueError("Saved drawing hash mismatch. Upload the drawing again.")
            context = ProjectContext(
                country=settings.country,
                region=settings.region,
                city=settings.city or None,
                planning_authority=settings.authority,
                ada_reference=True,
                site_address=settings.site_address or None,
                permit_date=settings.permit_date,
                facility_type=settings.facility_type or None,
                occupancy=settings.occupancy or None,
                work_type=settings.work_type,
                sprinklered=settings.sprinklered,
            )
            # Never translate a manually entered authority into an adopted ruleset.
            process(
                source,
                output,
                context,
                ["ada_2010"],
                settings.scale_mm_per_point,
                extra_coverage_notes=[
                    "ADA reference comparison explicitly requested by the user; "
                    "this does not establish legal applicability.",
                    "Local building code: not checked. No local rules selected by this web flow.",
                ],
            )
            artifact = CheckRunArtifact.load(output / "run.json")
            project.check_results = RunResult(
                id=run_id,
                revision=project.revision,
                source_sha256=drawing.sha256,
                report=artifact.report,
            )
            project.status = "complete"
            project.requires_new_run = False
            # Keep the exact saved settings with each run alongside engine provenance.
            (output / "project.json").write_text(
                project.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception as error:
            shutil.rmtree(output, ignore_errors=True)
            project.status = "error"
            project.error = str(error)
            self._write(project)
            raise
        return self._write(project)

    def download(self, project_id: UUID, run_id: UUID, filename: str) -> Path:
        if filename not in DOWNLOADS:
            raise ValueError("Unsupported download")
        project = self.get(project_id)
        current = project.check_results
        if (
            project.requires_new_run
            or current is None
            or current.id != run_id
            or current.revision != project.revision
        ):
            raise ValueError("Results are stale or unavailable. Run checks for the saved revision.")
        return self.folder / str(project_id) / "runs" / str(run_id) / filename
