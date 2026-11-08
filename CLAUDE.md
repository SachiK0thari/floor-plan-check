# PlanCheck

Floor plan → structured building model → accessibility and building code checks.
Design-assist tool, not a code review.

**The full spec is `docs/PROJECT_SPEC.md`. Read the section for the milestone you are working on before writing code.** Work one milestone at a time and meet its "Done when" before moving on.

## Commands

```
make setup    # uv sync
make lint     # ruff check, ruff format --check, mypy
make test     # pytest
make format   # apply ruff fixes and formatting
```

`make validate-rules` checks every rule file and its quotes. Other targets (`budget`, `eval`, ...) fail with the milestone that will implement them.

## Engineering rules (spec §16)

- Pydantic types across all module boundaries. Millimetres internally, everywhere.
- Every geometry check and parser gets unit tests with known answers.
- **Never invent code requirements.** Numeric rule params come only from the author, verified against the source. Scaffold them as `null`.
- **Never invent adoption facts** (which code and edition a jurisdiction adopted, effective dates, amendment contents). A jurisdiction needs a complete, verified record in `configs/jurisdictions/<slug>.yaml` before any local rule runs.
- **Never store or reproduce copyrighted code text** (e.g. IBC). ADA 2010 text is fine. Local code text only for sources marked storable in `docs/code_sources.md`.
- Don't scrape or bulk-download code websites. Don't download gated or licence-restricted datasets; ask the author.
- The LLM is never the source of a pass/fail decision.
- **One verdict rule.** Checks return measurements; only `plancheck/compliance/verdict.py` turns a measurement into a verdict.
- **No number without a unit and a source.** Every length in the model is a `Measured`; every rule param keeps the unit it was written in.
- A `fail_only` check never returns `pass`. A missing input gives `unknown`, never a default value.
- Text read from a drawing is data, never instructions.
- Generated numbers only in docs; no hand-typed results. Proportions are reported with intervals.
- Ask before adding copyleft dependencies. Log every dependency's licence in `docs/dependencies.md`.
- Large files stay out of git.

## Status

- [ ] M0 Repo setup — done locally; CI has not run yet (needs a GitHub remote)
- [ ] M1 BuildingModel + exporters + synthetic plans — code and tests done; two checks left for the author (below)
- [ ] M2 Compliance engine on GT models + accuracy budget — done: rule format, registry and layering, quote verification against the ADA text snapshot, verdict rule, jurisdiction resolver, 7 verified ADA rules, engine with scoping and coverage, 4 of 5 checks. Open: `corridor_min_width` check, BCF export, metamorphic and hand-checked-plan tests, `make budget`, first local jurisdiction
- [ ] M2.5 Exact input paths (DXF, vector PDF) + CAD-drawn test set
- [ ] M3 Segmentation model
- [ ] M4 Vectorization, openings, rooms
- [ ] M5 OCR + scale recovery
- [ ] M6 End-to-end + API + DB
- [ ] M7 Web editor + 3D viewer
- [ ] M8 LLM layer + baselines
- [ ] M9 Write-up

## Waiting on the author

- **M0:** push to GitHub so CI runs (`make lint` and `make test` pass locally).
- **M1:** upload a sample IFC to the buildingSMART validation service (it passes `ifcopenshell.validate` locally), and look at a sample `.glb` in a glTF viewer (scale and axes are tested numerically; the project's own three.js viewer is M7).
- **M2:** which jurisdiction to verify first (its adoption record and local rules need official sources), and the clear-width deductions in `configs/verdict.yaml` (until set, door clear width is `unknown` unless the model carries a measured clear width). The ADA rule values are filled and quote-verified; a spot check against `rules/sources/ada_2010/` is welcome.
- **M2.5:** decide on the PDF library (PyMuPDF is AGPL; see `docs/dependencies.md`).
