"""Versioned, self-contained inputs and results for a compliance run."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from plancheck import __version__
from plancheck.compliance.context import CheckContext
from plancheck.compliance.engine import Report, run
from plancheck.compliance.registry import RULES_DIR, LoadedRule, ResolvedRules
from plancheck.compliance.rules import Rule
from plancheck.jurisdiction.resolve import AdoptionRecord, load_adoption_records
from plancheck.model.types import BuildingModel, Measured

_ROOT = Path(__file__).resolve().parents[2]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _rule_digest(rule: Rule) -> str:
    data = json.dumps(rule.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class RuleSnapshot(_Base):
    rule: Rule
    ruleset: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _integrity(self) -> Self:
        if self.snapshot_sha256 != _rule_digest(self.rule):
            raise ValueError("rule snapshot does not match snapshot_sha256")
        return self

    @classmethod
    def capture(cls, loaded: LoadedRule) -> RuleSnapshot:
        try:
            path = loaded.path.relative_to(RULES_DIR).as_posix()
        except ValueError:
            path = loaded.path.name
        return cls(
            rule=loaded.rule.model_copy(deep=True),
            ruleset=loaded.ruleset,
            path=path,
            sha256=loaded.sha256,
            snapshot_sha256=_rule_digest(loaded.rule),
        )

    def loaded(self) -> LoadedRule:
        return LoadedRule(
            self.rule.model_copy(deep=True), self.ruleset, Path(self.path), self.sha256
        )


class VerdictConfiguration(_Base):
    """Effective values, including caller overrides rather than just YAML defaults."""

    guard_factor_k: float = Field(ge=0, allow_inf_nan=False)
    clear_width_deductions: dict[str, Measured]

    def context(self) -> CheckContext:
        return CheckContext(
            k=self.guard_factor_k,
            clear_width_deductions={
                key: value.model_copy(deep=True)
                for key, value in self.clear_width_deductions.items()
            },
        )


class EngineIdentity(_Base):
    version: str
    git_sha: str | None
    git_dirty: bool | None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    python_version: str
    installed_packages: dict[str, str]


def _engine_identity() -> EngineIdentity:
    # The source digest also identifies uncommitted/untracked Python changes. A Git
    # commit alone is insufficient in a dirty worktree or a source installation.
    digest = hashlib.sha256()
    for path in sorted((_ROOT / "plancheck").rglob("*.py")):
        digest.update(path.relative_to(_ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    sha = None
    dirty = None
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        sha = head.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass  # Installed packages need not have a Git checkout.
    packages = {
        distribution.metadata["Name"]: distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }
    return EngineIdentity(
        version=__version__,
        git_sha=sha,
        git_dirty=dirty,
        source_sha256=digest.hexdigest(),
        python_version=platform.python_version(),
        installed_packages=dict(sorted(packages.items())),
    )


class CheckRunArtifact(_Base):
    schema_version: Literal[1] = 1
    created_at: AwareDatetime
    model: BuildingModel
    rulesets: list[str]
    effective_rule_hashes: list[tuple[str, str]]
    rules: list[RuleSnapshot]
    # Preserve the resolver's input as well as its historical source layers, including
    # explicit not-runnable reasons on manually constructed ResolvedRules.
    resolved_rule_ids: list[str]
    source_rule_ids: list[str]
    resolution_notes: list[str]
    not_runnable: list[tuple[str, str]]
    adoption_records: list[AdoptionRecord]
    engine: EngineIdentity
    dependency_lockfile: str
    dependency_lockfile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verdict_configuration: VerdictConfiguration
    extra_coverage_notes: list[str]
    report: Report

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (
            self.rulesets != self.report.rulesets
            or self.effective_rule_hashes != self.report.fingerprint
        ):
            raise ValueError("run provenance does not match report rulesets/fingerprint")
        by_id = {snapshot.rule.id: snapshot for snapshot in self.rules}
        if len(by_id) != len(self.rules):
            raise ValueError("duplicate rule snapshots")
        for rule_id in self.source_rule_ids + self.resolved_rule_ids:
            if rule_id not in by_id:
                raise ValueError(f"rule snapshot missing for {rule_id}")
        for rule_id, sha256 in self.effective_rule_hashes:
            if rule_id not in by_id or by_id[rule_id].sha256 != sha256:
                raise ValueError(f"effective rule hash mismatch for {rule_id}")
        return self

    def save(self, path: Path) -> None:
        """Write JSON; filesystem errors propagate to the caller."""
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CheckRunArtifact:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def replay(self) -> Report:
        """Run captured inputs with the CURRENT engine/environment, not historical code."""
        loaded = {snapshot.rule.id: snapshot.loaded() for snapshot in self.rules}
        resolved = ResolvedRules(
            rulesets=list(self.rulesets),
            rules=[loaded[rule_id] for rule_id in self.resolved_rule_ids],
            source_rules=[loaded[rule_id] for rule_id in self.source_rule_ids],
            notes=list(self.resolution_notes),
            not_runnable=list(self.not_runnable),
        )
        report = run(
            self.model.model_copy(deep=True),
            resolved,
            self.verdict_configuration.context(),
            adoption_records=[r.model_copy(deep=True) for r in self.adoption_records],
            extra_coverage_notes=list(self.extra_coverage_notes),
        )
        return Report.model_validate_json(report.model_dump_json())


def create_run(
    model: BuildingModel,
    resolved: ResolvedRules,
    ctx: CheckContext | None = None,
    *,
    lockfile: Path | None = None,
    adoption_records: list[AdoptionRecord] | None = None,
    extra_coverage_notes: list[str] | None = None,
) -> CheckRunArtifact:
    """Execute and capture together so saved provenance describes the inputs used."""
    lockfile = lockfile if lockfile is not None else _ROOT / "uv.lock"
    lock_digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    context = ctx or CheckContext()
    settings = VerdictConfiguration(
        guard_factor_k=context.k, clear_width_deductions=context.clear_width_deductions
    ).model_copy(deep=True)
    records = load_adoption_records() if adoption_records is None else adoption_records
    records = [record.model_copy(deep=True) for record in records]
    captured_model = model.model_copy(deep=True)
    by_id: dict[str, LoadedRule] = {}
    for loaded in resolved.source_rules + resolved.rules:
        if loaded.rule.id in by_id and by_id[loaded.rule.id] != loaded:
            raise ValueError(f"conflicting source/effective rules for {loaded.rule.id}")
        by_id[loaded.rule.id] = loaded
    snapshots = [RuleSnapshot.capture(loaded) for loaded in by_id.values()]
    # Reconstruct from detached snapshots before execution, not after it.
    detached = {snapshot.rule.id: snapshot.loaded() for snapshot in snapshots}
    inputs = ResolvedRules(
        rulesets=list(resolved.rulesets),
        rules=[detached[r.rule.id] for r in resolved.rules],
        source_rules=[detached[r.rule.id] for r in resolved.source_rules],
        notes=list(resolved.notes),
        not_runnable=list(resolved.not_runnable),
    )
    notes = list(extra_coverage_notes or [])
    identity = _engine_identity()
    report = run(
        captured_model,
        inputs,
        settings.context(),
        adoption_records=records,
        extra_coverage_notes=notes,
    )
    return CheckRunArtifact(
        schema_version=1,
        created_at=datetime.now(UTC),
        model=captured_model,
        rulesets=list(report.rulesets),
        effective_rule_hashes=list(report.fingerprint),
        rules=snapshots,
        resolved_rule_ids=[r.rule.id for r in inputs.rules],
        source_rule_ids=[r.rule.id for r in inputs.source_rules],
        resolution_notes=list(inputs.notes),
        not_runnable=list(inputs.not_runnable),
        adoption_records=records,
        engine=identity,
        dependency_lockfile=lockfile.name,
        dependency_lockfile_sha256=lock_digest,
        verdict_configuration=settings,
        extra_coverage_notes=notes,
        report=Report.model_validate_json(report.model_dump_json()),
    )
