"""Real exact-input runs, explicit reference selection and stale download prevention."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import ezdxf
import pytest

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.evaluation.plans import corridor_plan
from plancheck.export.dxf import export_dxf
from plancheck.ingest.vector_pdf import export_vector_pdf
from plancheck.jurisdiction.proposal import ProjectSettings
from plancheck.local_projects import DOWNLOADS, LocalProjects, SaveRequest


def confirmed() -> ProjectSettings:
    return ProjectSettings(
        country="IN",
        region="Maharashtra",
        authority="Manually named authority",
        permit_date=date(2026, 1, 1),
        confirmed=True,
        ada_reference=True,
        facility_type="commercial_facility",
        work_type="new",
    )


@pytest.mark.parametrize("kind", ["dxf", "pdf"])
def test_saved_drawing_runs_and_downloads_become_stale(tmp_path: Path, kind: str) -> None:
    store = LocalProjects(tmp_path / "projects")
    path = tmp_path / ("drawing." + kind)
    model = corridor_plan(800, 700)
    (export_dxf if kind == "dxf" else export_vector_pdf)(model, path)
    drawing = store.upload(path.name, path.read_bytes())
    project = store.save(SaveRequest(settings=confirmed(), upload_id=drawing.id))
    assert project.drawing is not None
    assert project.status == "ready"
    assert not project.availability["adoption_available"]
    # Reopen with a fresh store to prove neither source bytes nor settings rely on memory.
    store = LocalProjects(store.folder)
    completed = store.run(project.id, project.revision)
    result = completed.check_results
    assert result is not None
    assert completed.status == "complete"
    assert not completed.requires_new_run
    assert result.source_sha256 == drawing.sha256
    assert result.report.rulesets == ["ada_2010"]
    assert any(f.verdict == "fail" for f in result.report.findings)
    assert any(
        "Local building code: not checked" in note for note in result.report.coverage["notes"]
    )
    for filename in DOWNLOADS:
        assert store.download(project.id, result.id, filename).stat().st_size > 0
    artifact = CheckRunArtifact.load(store.download(project.id, result.id, "run.json"))
    assert artifact.model.project.country == "IN"
    assert artifact.model.project.planning_authority == project.settings.authority
    assert artifact.model.project.jurisdiction is None
    assert artifact.model.project.ada_reference
    # Renaming preserves the results; a permit date change invalidates them.
    renamed = store.save(SaveRequest(id=project.id, name="Renamed", settings=confirmed()))
    assert renamed.check_results == result
    changed = store.save(
        SaveRequest(
            id=project.id,
            settings=confirmed().model_copy(update={"permit_date": date(2025, 1, 1)}),
        )
    )
    assert changed.revision == project.revision + 1
    assert changed.check_results is None
    with pytest.raises(ValueError, match="stale"):
        store.download(project.id, result.id, "report.html")
    with pytest.raises(ValueError, match="changed"):
        store.run(project.id, project.revision)


def test_no_implicit_ada_no_unconfirmed_run_and_source_change_invalidates(tmp_path: Path) -> None:
    store = LocalProjects(tmp_path / "projects")
    path = export_dxf(corridor_plan(), tmp_path / "source.dxf")
    drawing = store.upload(path.name, path.read_bytes())
    settings = confirmed().model_copy(update={"ada_reference": False})
    project = store.save(SaveRequest(settings=settings, upload_id=drawing.id))
    with pytest.raises(ValueError, match="Explicitly select ADA"):
        store.run(project.id, project.revision)
    unconfirmed = store.save(
        SaveRequest(id=project.id, settings=confirmed().model_copy(update={"confirmed": False}))
    )
    with pytest.raises(ValueError, match="confirm"):
        store.run(project.id, unconfirmed.revision)
    second_path = export_dxf(corridor_plan(800, 700), tmp_path / "replacement.dxf")
    second_drawing = store.upload(second_path.name, second_path.read_bytes())
    replacement = store.save(
        SaveRequest(id=project.id, settings=unconfirmed.settings, upload_id=second_drawing.id)
    )
    assert replacement.revision == unconfirmed.revision + 1
    assert replacement.requires_new_run
    assert replacement.evidence == second_drawing.evidence
    assert replacement.drawing != drawing


def test_failed_geometry_and_tampered_drawing_never_produce_results(tmp_path: Path) -> None:
    store = LocalProjects(tmp_path / "projects")
    path = tmp_path / "ordinary.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_text("Country: India")
    doc.saveas(path)
    drawing = store.upload(path.name, path.read_bytes())
    project = store.save(SaveRequest(settings=confirmed(), upload_id=drawing.id))
    with pytest.raises(ValueError, match="no supported exact wall entities"):
        store.run(project.id, project.revision)
    failed = store.get(project.id)
    assert failed.status == "error"
    assert failed.error
    assert failed.check_results is None
    assert not list((store.folder / str(project.id) / "runs").glob("*/run.json"))
    (store.folder / "uploads" / drawing.id).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.run(project.id, project.revision)
    with pytest.raises(ValueError, match="Unsupported download"):
        store.download(project.id, uuid4(), "../../uploads")


def test_unknown_project_context_is_not_filled_from_fixture(tmp_path: Path) -> None:
    store = LocalProjects(tmp_path / "projects")
    path = export_dxf(corridor_plan(), tmp_path / "source.dxf")
    drawing = store.upload(path.name, path.read_bytes())
    settings = confirmed().model_copy(update={"facility_type": "", "work_type": None})
    project = store.save(SaveRequest(settings=settings, upload_id=drawing.id))
    completed = store.run(project.id, project.revision)
    assert completed.check_results is not None
    report = completed.check_results.report
    assert any(f.verdict == "unknown" for f in report.findings)
