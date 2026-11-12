# Saved check runs

Use `create_run` instead of separately running checks and attaching metadata later.
It executes the checks with detached input snapshots and returns a versioned
`CheckRunArtifact`. With an existing `BuildingModel` named `model`:

```python
from pathlib import Path

from plancheck.compliance.artifacts import CheckRunArtifact, create_run
from plancheck.compliance.registry import resolve

artifact = create_run(model, resolve(["ada_2010"]))
artifact.save(Path("check-run.json"))
saved = CheckRunArtifact.load(Path("check-run.json"))
assert saved.replay() == saved.report
```

The JSON contains:

- The complete building model, including project context and missing values.
- Ordered rulesets, effective rule IDs/hashes, full original rule snapshots,
  amendment source layers, resolver notes, and not-runnable reasons.
- The adoption records actually supplied to the check run.
- Engine version, Git SHA and dirty status when Git is available, a digest of the
  installed package's Python source files, Python version, and installed package
  versions. The source digest includes uncommitted and untracked Python files.
- The dependency lockfile's name and SHA-256, defaulting to the repository's
  `uv.lock`. A missing lockfile is an error; pass `lockfile=Path(...)` for an
  explicitly located lockfile in an installed environment.
- Effective verdict settings: guard factor and typed clear-width deductions,
  including caller overrides, uncertainties, units implied by `Measured`, and
  provenance. Derived per-rule door dependencies are reconstructed from the rules.
- The complete report: findings, groups, coverage, missing-input reasons,
  exceptions, citations, governing requirements, and amendment audit records.
- Schema version and a timezone-aware UTC creation timestamp.

Pass a `CheckContext` as the third argument to capture runtime verdict overrides.
`adoption_records=` and `extra_coverage_notes=` accept the same inputs as `run`.
Adoption records are read once when omitted, then explicitly passed to execution.
No drawing, dataset, or external code-source files are downloaded or embedded.
Paths to source drawings remain model metadata; their image bytes are not included.

`save` writes UTF-8 JSON to the requested path; its parent directory must exist.
`load` validates the schema, rule snapshot digests, and consistency of the report's
rulesets/fingerprint with saved rule provenance. The snapshot digest hashes the
canonical rule model; the original file hash remains separate because YAML
formatting and in-memory rule edits can differ from that canonical representation.
These consistency checks are not a signature or authentication mechanism.

`replay` reconstructs the saved rules, model, adoption records, and verdict settings
without reading current rule/config files. It uses the **current engine and Python
environment**; it does not install historical dependencies or restore source code.
For historical reproduction, restore the identified source and matching lockfile
and compare runtime package versions. A dirty Git SHA alone cannot recover local
edits; retain those sources alongside the artifact. The recorded source digest
identifies them but does not embed them.

Reports are normalized through JSON when captured so free-form coverage fields
(such as tuple-valued applicability entries) round-trip consistently. Save large
local artifacts under the already ignored `out/` directory, creating it first.
