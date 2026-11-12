"""Saved runs retain the inputs that produced results, independently of live files."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from plancheck import __version__
from plancheck.compliance.artifacts import CheckRunArtifact, create_run
from plancheck.compliance.context import CheckContext
from plancheck.compliance.registry import ResolvedRules, resolve
from plancheck.compliance.verdict import Verdict
from plancheck.jurisdiction.resolve import AdoptionRecord
from plancheck.model.types import BuildingModel, Measured, ProjectContext
from tests.test_multi_code import CODE, EDITION, SLUG, base_and_amendment


@pytest.fixture
def model(two_rooms: BuildingModel) -> BuildingModel:
    return two_rooms.model_copy(
        update={
            "project": ProjectContext(
                facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
            ),
            "rooms": [
                r.model_copy(update={"room_type": None}) if r.id == "R1" else r
                for r in two_rooms.rooms
            ],
        }
    )


@pytest.fixture
def ada() -> ResolvedRules:
    return resolve(["ada_2010"])


def test_saved_run_round_trip_preserves_results_and_effective_settings(
    model: BuildingModel, ada: ResolvedRules, tmp_path: Path
) -> None:
    lock = tmp_path / "test.lock"
    lock.write_bytes(b"test dependency lock\n")
    deduction = Measured(value_mm=50, sigma_mm=5, source="user")
    ctx = CheckContext(k=3, clear_width_deductions={"swing": deduction})
    artifact = create_run(
        model, ada, ctx, lockfile=lock, adoption_records=[], extra_coverage_notes=["test run note"]
    )
    path = tmp_path / "run.json"
    artifact.save(path)
    restored = CheckRunArtifact.load(path)
    assert restored == artifact
    assert restored.model == model
    assert restored.model.project.permit_date == date(2026, 1, 1)
    assert restored.verdict_configuration.guard_factor_k == 3
    assert restored.verdict_configuration.clear_width_deductions == {"swing": deduction}
    assert restored.dependency_lockfile_sha256 == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert restored.engine.version == __version__
    assert len(restored.engine.source_sha256) == 64
    assert restored.engine.python_version
    assert restored.engine.installed_packages
    assert restored.created_at.utcoffset() is not None
    assert restored.effective_rule_hashes == restored.report.fingerprint
    assert restored.rulesets == ["ada_2010"]
    assert restored.report.coverage["unresolved"]
    assert restored.report.coverage["surfaced_exceptions"]
    assert "test run note" in restored.report.coverage["notes"]
    width = next(
        f for f in restored.report.for_rule("ada2010.door-clear-width") if f.element_ids == ["D1"]
    )
    assert width.measured is not None
    assert width.measured.value_mm == pytest.approx(914.4 - 50)
    assert width.measured.sigma_mm == 5
    assert restored.replay() == restored.report


def test_replay_is_independent_of_live_rules_config_and_caller_mutations(
    model: BuildingModel, ada: ResolvedRules, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = CheckContext(
        k=2, clear_width_deductions={"swing": Measured(value_mm=50, sigma_mm=0, source="user")}
    )
    artifact = create_run(model, ada, ctx, adoption_records=[])
    ctx.clear_width_deductions.clear()
    model.rooms.clear()
    ada.rules.clear()
    ada.source_rules.clear()
    monkeypatch.setenv("PLANCHECK_CONFIG_DIR", str(tmp_path / "nonexistent"))
    assert artifact.model.rooms
    assert artifact.verdict_configuration.clear_width_deductions
    assert artifact.replay() == artifact.report


def test_missing_permit_date_and_exception_reasons_survive_json(
    two_rooms: BuildingModel, ada: ResolvedRules, tmp_path: Path
) -> None:
    model = two_rooms.model_copy(
        update={"project": ProjectContext(facility_type="commercial_facility")}
    )
    artifact = create_run(
        model, ada, CheckContext(k=2, clear_width_deductions={}), adoption_records=[]
    )
    path = tmp_path / "unknown.json"
    artifact.save(path)
    restored = CheckRunArtifact.load(path)
    assert restored == artifact
    assert restored.model.project.permit_date is None
    assert all(
        f.verdict is Verdict.UNKNOWN and "permit_date" in (f.reason or "")
        for f in restored.report.findings
    )
    assert restored.report.coverage["unknown_applicability"]
    assert restored.report.coverage["surfaced_exceptions"]
    assert restored.replay() == restored.report


def test_amendment_sources_and_adoptions_are_self_contained(
    model: BuildingModel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from plancheck.compliance.registry import RULES_DIR

    root = tmp_path / "rules"
    shutil.copytree(RULES_DIR / "ada_2010", root / "ada_2010")
    resolved = base_and_amendment(root, "replace")
    record = AdoptionRecord(
        name="Synthetic authority (test only)",
        slug=SLUG,
        level="place",
        geoid="TEST",
        base_code=CODE,
        base_edition=EDITION,
        effective_date=date(2010, 1, 1),
        adopting_reference="TEST",
        source_url="https://example.test/adoption",
        retrieved_on=date(2026, 1, 1),
        verified_by="Synthetic fixture, not real adoption facts",
    )
    model = model.model_copy(
        update={
            "project": model.project.model_copy(
                update={"jurisdiction": SLUG, "jurisdiction_source": "user"}
            )
        }
    )
    artifact = create_run(
        model, resolved, CheckContext(k=2, clear_width_deductions={}), adoption_records=[record]
    )
    path = tmp_path / "amended.json"
    artifact.save(path)
    restored = CheckRunArtifact.load(path)
    assert {r.rule.id for r in restored.rules} >= {"test.base-width", "test.local-width"}
    assert restored.report.amendments[0].status == "applied"
    assert restored.adoption_records == [record]
    shutil.rmtree(root)
    monkeypatch.setenv("PLANCHECK_CONFIG_DIR", str(tmp_path / "nonexistent"))
    assert restored.replay() == restored.report


def test_snapshot_tampering_and_unknown_schema_are_rejected(
    model: BuildingModel, ada: ResolvedRules
) -> None:
    artifact = create_run(
        model, ada, CheckContext(k=2, clear_width_deductions={}), adoption_records=[]
    )
    raw = artifact.model_dump(mode="json")
    raw["rules"][0]["rule"]["title"] = "tampered"
    with pytest.raises(ValidationError, match="snapshot_sha256"):
        CheckRunArtifact.model_validate(raw)
    raw = artifact.model_dump(mode="json")
    raw["schema_version"] = 999
    with pytest.raises(ValidationError, match="schema_version"):
        CheckRunArtifact.model_validate(raw)


def test_lockfile_is_required_and_changes_are_recorded(
    model: BuildingModel, ada: ResolvedRules, tmp_path: Path
) -> None:
    lock = tmp_path / "test.lock"
    ctx = CheckContext(k=2, clear_width_deductions={})
    with pytest.raises(FileNotFoundError):
        create_run(model, ada, ctx, lockfile=lock, adoption_records=[])
    lock.write_bytes(b"first lock")
    first = create_run(model, ada, ctx, lockfile=lock, adoption_records=[])
    lock.write_bytes(b"second lock")
    second = create_run(model, ada, ctx, lockfile=lock, adoption_records=[])
    assert first.dependency_lockfile_sha256 != second.dependency_lockfile_sha256


def test_engine_version_and_source_digest_are_available_without_git(
    model: BuildingModel, ada: ResolvedRules, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import Any

    import plancheck.compliance.artifacts as artifacts

    def no_git(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("git unavailable")

    monkeypatch.setattr(artifacts.subprocess, "run", no_git)
    artifact = create_run(
        model, ada, CheckContext(k=2, clear_width_deductions={}), adoption_records=[]
    )
    assert artifact.engine.git_sha is None
    assert artifact.engine.git_dirty is None
    assert artifact.engine.version == __version__
    assert len(artifact.engine.source_sha256) == 64
