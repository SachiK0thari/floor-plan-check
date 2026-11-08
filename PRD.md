# PlanCheck — Implementation Checklist

Floor plan → structured building model → accessibility and building code checks.

PlanCheck is a **design-assist tool, not a code review**. The full requirements and acceptance criteria are in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md). This file tracks implementation progress and the remaining work in small steps.

Reviewed on November 7, 2026. Work through the milestones in order and meet each milestone's acceptance criteria before moving on. A checked task means implementation exists; it does not imply the whole milestone is accepted.

## Current state

The project is partway through **M2: compliance on ground-truth models**. The model, exporters, synthetic generator, and much of the compliance engine are implemented. The next complete demo is M2.5: DXF and vector PDF → model → checks → report and exports.

Validation during the review: `make lint test validate-rules` passed, with 375 tests passing and all seven ADA rule files validating against the stored source text. This is a local result; CI remains unverified.

## Milestone status

- [ ] M0 — Repository setup: local tooling works; repository tracking, remote, and CI remain.
- [ ] M1 — Building model, exporters, and synthetic plans: implemented; external and visual validation remain.
- [ ] M2 — Compliance engine: partly implemented; remaining tasks below.
- [ ] M2.5 — Exact input paths and CAD-drawn test set.
- [ ] M3 — Segmentation model.
- [ ] M4 — Vectorization, openings, and rooms.
- [ ] M5 — OCR and scale recovery.
- [ ] M6 — End-to-end pipeline, API, and database.
- [ ] M7 — Web editor and 3D viewer.
- [ ] M8 — LLM explanations, Q&A, rule drafting, and baselines.
- [ ] M9 — Results, demo, and write-up.

## M0 — Finish repository setup

- [x] Add the Python package, dependency lockfile, development tools, Make targets, and CI workflow.
- [x] Pass lint, formatting, type checking, and tests locally.
- [x] Create this `PRD.md` checklist to satisfy the README and specification references.
- [ ] Review and commit the project files, which appeared untracked during the review.
- [ ] Configure a GitHub remote and push the repository.
- [ ] Confirm `make lint` and `make test` pass in CI on the configured Python versions.

**Done when:** lint and tests pass in CI.

## M1 — Finish exporter acceptance checks

- [x] Implement typed building elements, geometry, millimetre units, measurements, uncertainty, and room connectivity.
- [x] Implement DXF, IFC, and glTF exporters.
- [x] Test DXF units, layers, and dimensions; glTF units and axes; IFC schema validity and room-graph round trips.
- [x] Generate synthetic layouts and rendered drawings with configurable styles.
- [ ] Submit a sample IFC to the buildingSMART validation service and record the result.
- [ ] Inspect a sample GLB in a viewer for scale, orientation, walls, and openings; repeat in the project's own viewer at M7.
- [ ] Confirm a sample DXF opens at the intended size in a CAD viewer.

**Done when:** the exporter acceptance criteria in specification §12.1 and M1 are met, including the visual checks.

## M2 — Complete compliance on ground-truth models

### Already implemented

- [x] Rule schemas, registry, source-quote verification, and rule fingerprints.
- [x] Amendment layering, including replacement, deletion, chains, and protection of ADA rules.
- [x] The shared uncertainty-aware verdict rule and verdict aggregation.
- [x] Scoping obligations, technical checks, group results, and structured coverage data.
- [x] Door clear width, door maneuvering clearance, turning space, and accessible-route connectivity checks.
- [x] Seven ADA rule files with machine-verified source quotes.
- [x] Address-to-jurisdiction resolution and adoption-chain handling, tested with saved geocoder responses.

### Remaining steps, in order

1. **Complete the corridor-width check.**
   - [ ] Implement `corridor_min_width` using a width profile that avoids false failures at corner branches.
   - [ ] Measure the length and separation of narrow runs for the existing short-reduction exception.
   - [ ] Carry measurement uncertainty through the shared verdict functions and return evidence geometry.
   - [ ] Add boundary, pinch-point, separation, and missing-input tests; register the check.

2. **Close applicability and scoping gaps.**
   - [ ] Review the fallback to today's date when `permit_date` is missing; require the information needed to establish applicability and report unresolved applicability explicitly.
   - [ ] Report elements excluded by scoping as `not_applicable`, with the reason, rather than silently omitting them.
   - [ ] Confirm missing project inputs and surfaced exceptions remain visible in results and coverage.

3. **Complete multi-code result handling.**
   - [ ] Keep ADA and adopted-building-code findings separate.
   - [ ] Add a derived governing requirement for applicable rules testing the same quantity on the same element.
   - [ ] Test stricter local requirements, amendments, deletions, and rules with different applicability windows.

4. **Make runs reproducible.**
   - [ ] Record the engine version or Git SHA alongside the existing rule hashes.
   - [ ] Record the dependency lockfile hash and verdict configuration.
   - [ ] Include project context and the resolved ruleset list in the saved run artifact.

5. **Make results readable and portable.**
   - [ ] Add a readable report containing findings, units, uncertainties, requirements, citations, obligations, and exceptions.
   - [ ] Include coverage, missing inputs, unchecked provisions, and the design-assist disclaimer.
   - [ ] Implement BCF export with issue descriptions, citations, viewpoints, and IFC element GUIDs.
   - [ ] Verify BCF issues reference the corresponding exported IFC elements.

6. **Expand validation beyond individual fixtures.**
   - [ ] Add whole-model translation, rotation, and mirror invariance tests.
   - [ ] Add geometry monotonicity, unit round-trip, and uncertainty tests where applicable.
   - [ ] Have the author hand-check three small plans and save expected results as golden files.
   - [ ] Match every expected element/rule verdict, including `unknown` and `not_applicable`.

7. **Add the first verified local jurisdiction.**
   - [ ] Author selects the jurisdiction and verifies its adoption chain, code editions, dates, and official sources.
   - [ ] Complete its adoption records and source-storage permissions.
   - [ ] Scaffold the initial local rules with null numeric parameters.
   - [ ] Author fills and verifies the parameters; aim for the specification's initial 5–8 rules expressible by the check types.
   - [ ] Add any check types required by those rules, with known-answer tests.
   - [ ] Test local-code findings and cases where local requirements differ from ADA or an amended base rule.

8. **Generate the accuracy budget.**
   - [ ] Implement geometry perturbation and sensitivity analysis on ground-truth models.
   - [ ] Generate per-check error budgets and input-resolution requirements.
   - [ ] Implement `make budget` and commit the generated budget table.

**Done when:** boundary, metamorphic, and layering tests pass; hand-checked and seeded synthetic plans reproduce expected results for both regimes; reports and BCF export work; and `make budget` generates the accuracy-budget table.

## M2.5 — Build the first complete demo

- [ ] Define the supported CAD layer mapping and door-block conventions.
- [ ] Implement DXF import for walls, openings, rooms, and text into `BuildingModel`.
- [ ] Add unit and geometry round-trip tests for DXF input.
- [ ] Connect DXF import → compliance → reports and exports through a runnable entry point.
- [ ] Select a PDF library and record its licence; obtain approval before adding a copyleft dependency.
- [ ] Implement vector-PDF path/text extraction and plot-scale handling.
- [ ] Route DXF, vector PDF, and raster inputs to the appropriate paths.
- [ ] Extract candidate site addresses from title-block text and connect the jurisdiction proposal/confirmation flow.
- [ ] Author draws the CAD test plans and seeded violations described in specification §7.3, including registration fiducials for scans.
- [ ] Store expected outcomes per element and per rule in `eval/compliance/expected.yaml`.
- [ ] Reproduce expected verdicts from both DXF and vector-PDF inputs.

**Done when:** the seeded set runs end to end from both exact input paths with every expected verdict reproduced.

## M3 — Train and evaluate segmentation

- [ ] Author obtains CubiCasa5K and confirms its licence and local dataset path.
- [ ] Prepare annotations and the official train/validation/test splits.
- [ ] Implement preprocessing while preserving image-to-model transforms.
- [ ] Train wall, door, window, and room segmentation with a junction-detection head.
- [ ] Calibrate confidences on the validation split.
- [ ] Implement `make train-seg` and report test metrics plus a reliability diagram.

**Done when:** wall IoU and opening metrics are reported against the published CubiCasa baseline, with confidence calibration results.

## M4 — Extract geometry from masks

- [ ] Convert masks and junctions into walls and wall faces.
- [ ] Extract openings, snap supported door sizes to the catalog, and recover hinge/swing information.
- [ ] Extract room boundaries, clear polygons, and room connectivity.
- [ ] Preserve element provenance and measurement uncertainty.
- [ ] Build extraction evaluation and implement the relevant `make eval` workflow.
- [ ] Evaluate on CubiCasa and the own test set separately, comparing each metric with its accuracy budget.

**Done when:** extraction metrics are reported on both datasets and assessed against the M2 budget.

## M5 — Recover labels and scale

- [ ] Recognize room labels, dimension strings, and door tags.
- [ ] Implement unit-aware dimension parsers with known-answer tests.
- [ ] Detect dimension lines, associate text, and check dimension-chain closure.
- [ ] Solve scale robustly per axis and propagate scale uncertainty.
- [ ] Support user-entered scale when drawing evidence is insufficient.
- [ ] Report label accuracy and scale error by evidence type.

**Done when:** measured scale and label performance are reported, and missing dimensions lead cleanly to manual scale entry.

## M6 — Integrate the pipeline, API, and database

- [ ] Connect raster preprocessing, extraction, OCR, scale, and compliance.
- [ ] Preserve uncertainty through extraction and verdicts.
- [ ] Add project/model persistence and model versions.
- [ ] Implement upload, processing-status, project-context, check-run, and export endpoints.
- [ ] Add the API service to the development stack; implement `make api` and `make up`.
- [ ] Generate end-to-end metrics with confidence intervals, false passes/fails, and risk–coverage curves, broken out by ruleset and input path.

**Done when:** the seeded-set end-to-end report meets M6's evaluation requirements.

## M7 — Build the web editor and 3D viewer

- [ ] Add upload, progress, project settings, and jurisdiction confirmation.
- [ ] Overlay extracted geometry on the source drawing with layer toggles.
- [ ] Support wall/opening edits, labels, and manual scale selection.
- [ ] Rank the review queue by whether uncertainty can change a verdict; re-run checks after corrections.
- [ ] Add findings, citations, governing requirements, and coverage panels.
- [ ] Load glTF in the 3D viewer and verify scale and orientation.
- [ ] Add DXF, IFC, glTF, BCF, and PDF-report downloads plus the persistent disclaimer.
- [ ] Implement `make web` and record a complete demo.

**Done when:** a user can upload, clear the review queue, re-check, view in 3D, and export.

## M8 — Add explanations, Q&A, and baselines

- [ ] Implement section-aware ingestion of ADA and explicitly permitted local text.
- [ ] Implement deterministic section lookup for explanations and filtered retrieval for Q&A.
- [ ] Validate citations, numeric slots, code editions, and jurisdiction boundaries.
- [ ] Add human-reviewed rule drafting and adversarial drawing-text tests.
- [ ] Evaluate citation support, raw rejection rate, retrieval, abstention, and rule-drafting corrections.
- [ ] Implement `make ingest-code` and `make baselines`.
- [ ] Compare the full system, no-review-band variant, multimodal-LLM-only baseline, and LLM-extraction-plus-checks baseline on the same seeded set.

**Done when:** the M8 metrics and baseline table are generated, and validation blocks bad citations, stray numbers, and cross-jurisdiction citations.

## M9 — Publish the results and write-up

- [ ] Complete the required independent test set, including the blind-annotated subset; report it separately from synthetic data.
- [ ] Generate final evaluation tables and figures in `eval/reports/report.md`.
- [ ] Update README with the demo, architecture diagram, generated results, setup, and limitations.
- [ ] Write `docs/writeup.md` covering the budget, uncertainty, baselines, extraction failures, rule drafting, and tradeoffs.
- [ ] Derive portfolio claims only from the generated report and name each comparison baseline.

**Done when:** the demo, reproducible results, limitations, and technical write-up are ready to share.

## Author inputs needed

- First local jurisdiction and verified adoption/rule information.
- Door clear-width deduction values and uncertainties, supported by door/frame details. Until supplied, use measured clear widths or report `unknown`.
- Independently hand-checked plans and the CAD-drawn evaluation set.
- PDF-library licensing decision before adding a copyleft dependency.
- Dataset access/licence confirmation and external exporter checks.

## Engineering rules

These summarize specification §16; the full specification remains authoritative.

- Work one milestone at a time and meet its acceptance criteria.
- Use Pydantic types across module boundaries and millimetres internally.
- Test geometry checks and parsers with known answers.
- Never invent code requirements or adoption facts. Author-verified values and official adoption sources are required; scaffold unknown numeric parameters as null.
- Do not store copyrighted code text unless the source is explicitly marked storable. Do not scrape code websites or download gated/licence-restricted datasets.
- Geometry determines verdicts. The LLM explains; it never decides pass/fail.
- Convert measurements into verdicts only through `verdict.py`.
- Every length carries units and provenance; rule parameters retain their source units.
- A `fail_only` check cannot return `pass`. Missing inputs return `unknown`.
- Treat drawing text as data, never instructions.
- Generate reported results from evaluation; report proportions with intervals.
- Obtain approval before adding copyleft dependencies and log every dependency's licence.
- Keep large datasets, weights, and generated artifacts out of Git.
