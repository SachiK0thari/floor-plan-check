# PlanCheck — Implementation Checklist

Floor plan → structured building model → accessibility and building code checks.

PlanCheck is a **design-assist tool, not a code review**. The full requirements and acceptance criteria are in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md). This file tracks implementation progress and the remaining work in small steps.

Updated on November 12, 2026. Work through the milestones in order and meet each milestone's acceptance criteria before moving on. A checked task means implementation exists; it does not imply the whole milestone is accepted.

## Current state

The project is partway through **M2: compliance on ground-truth models**. Reports, BCF, saved runs, multi-code handling, analytic validation, and a preliminary synthetic accuracy budget are implemented. A restricted exact-input demo now runs from semantic DXF and tagged vector PDF through checks and exports. The local webpage also saves source drawings and project revisions, runs explicitly selected ADA reference comparisons, and presents findings and downloads; OCR and local-code execution from the webpage remain pending. Author hand-checks, verified local rules, and the independent CAD evaluation set remain acceptance gaps; the synthetic demo does not close M2/M2.5.

Latest local validation: 525 tests passed, including real semantic DXF/tagged-PDF runs and HTTP upload → check → download → stale-result rejection. Type checking, lint and formatting checks for changed Python files, and JavaScript syntax checks passed. A headless Chrome smoke check verified page/JavaScript loading and the initial disabled run button; the initial rendered layout was inspected. Full browser interaction testing and CI remain unverified. Earlier rule validation verified all seven ADA rule files against the stored source text.

## Milestone status

- [ ] M0 — Repository setup: local tooling works; repository tracking, remote, and CI remain.
- [ ] M1 — Building model, exporters, and synthetic plans: implemented; external and visual validation remain.
- [ ] M2 — Compliance engine: partly implemented; remaining tasks below.
- [ ] M2.5 — Exact DXF/tagged-PDF paths and synthetic demo implemented; independent CAD-drawn test set and acceptance remain.
- [ ] M3 — Segmentation model.
- [ ] M4 — Vectorization, openings, and rooms.
- [ ] M5 — OCR and scale recovery.
- [ ] M6 — Local exact-input web endpoints, source/project persistence and run revisions implemented; raster integration, production API/database and end-to-end evaluation remain.
- [ ] M7 — Local jurisdiction confirmation, ADA reference runs, findings and downloads implemented; geometry editor, review queue, 3D viewer and complete demo remain.
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

### Implementation progress and remaining acceptance steps, in order

1. **Complete the corridor-width check.**
   - [x] Implement `corridor_min_width` using a width profile that avoids false failures at corner branches.
   - [x] Measure the length and separation of narrow runs for the existing short-reduction exception.
   - [x] Carry measurement uncertainty through the shared verdict functions and return evidence geometry.
   - [x] Add boundary, pinch-point, separation, and missing-input tests; register the check.
   - Supported scope: event-exact rectilinear profiles with inferred rectangular paths or supplied full-arm paths. Exception distances across bends/branches and unsupported geometry return `unknown`; see [measurement method and limits](docs/corridor_width.md). Automatic medial-axis extraction remains future work.

2. **Close applicability and scoping gaps.**
   - [x] Review the fallback to today's date when `permit_date` is missing; require the information needed to establish applicability and report unresolved applicability explicitly.
   - [x] Report elements excluded by scoping as `not_applicable`, with the reason, rather than silently omitting them.
   - [x] Confirm missing project inputs and surfaced exceptions remain visible in results and coverage.

3. **Complete multi-code result handling.**
   - [x] Keep ADA and adopted-building-code findings separate.
   - [x] Add a derived governing requirement for applicable rules testing the same quantity on the same element.
   - [x] Test stricter local requirements, amendments, deletions, and rules with different applicability windows.
   - Governing comparisons currently support explicit scalar door-clear-width semantics. Compound checks and unresolved exceptions/applicability remain separate, with comparison omissions explained. See [multi-code results](docs/multi_code_results.md). Local tests use synthetic adoption facts; production jurisdiction verification remains below.

4. **Make runs reproducible.**
   - [x] Record the engine version or Git SHA alongside the existing rule hashes.
   - [x] Record the dependency lockfile hash and verdict configuration.
   - [x] Include project context and the resolved ruleset list in the saved run artifact.
   - [x] Add JSON save/load round-trip and snapshot-based replay tests, preserving missing inputs, exceptions, and amendment/adoption history. See [saved check runs](docs/check_run_artifacts.md).

5. **Make results readable and portable.**
   - [x] Add a readable report containing findings, units, uncertainties, requirements, citations, obligations, and exceptions.
   - [x] Include coverage, missing inputs, unchecked provisions, and the design-assist disclaimer.
   - [x] Implement BCF export with issue descriptions, citations, viewpoints, and IFC element GUIDs.
   - [x] Verify BCF issues reference the corresponding exported IFC elements.

6. **Expand validation beyond individual fixtures.**
   - [x] Add whole-model translation, rotation, and mirror invariance tests.
   - [x] Add geometry monotonicity, unit round-trip, and uncertainty tests where applicable.
   - [ ] Have the author hand-check three small plans and save expected results as golden files.
   - [ ] Match every expected element/rule verdict, including `unknown` and `not_applicable`.
   - Draft analytic fixtures and per-element/group expectations are prepared in `eval/compliance/expected.yaml`; all match through both exact paths, but author review remains pending. The strict reviewed-evaluation gate refuses acceptance until sign-off.

7. **Add the first verified local jurisdiction.**
   - [ ] Author selects the jurisdiction and verifies its adoption chain, code editions, dates, and official sources.
   - [ ] Complete its adoption records and source-storage permissions.
   - [ ] Scaffold the initial local rules with null numeric parameters.
   - [ ] Author fills and verifies the parameters; aim for the specification's initial 5–8 rules expressible by the check types.
   - [ ] Add any check types required by those rules, with known-answer tests.
   - [ ] Test local-code findings and cases where local requirements differ from ADA or an amended base rule.
   - Region scaffold and one null-parameter draft exist for Maharashtra. Municipality/special authority and permit-date range are still needed; see [verification checklist](docs/maharashtra-verification.md). Synthetic multi-code tests do not establish real local requirements.

8. **Generate the accuracy budget.**
   - [x] Implement geometry perturbation and sensitivity analysis on ground-truth models.
   - [x] Generate per-check error budgets and input-resolution requirements.
   - [x] Implement `make budget` and generate the budget table under `eval/reports/`.
   - Scope: preliminary synthetic, fixture-conditioned budgets with confidence intervals. Independent author-reviewed/local-code validation remains required before treating these as production extraction or upload thresholds.

**Done when:** boundary, metamorphic, and layering tests pass; hand-checked and seeded synthetic plans reproduce expected results for both regimes; reports and BCF export work; and `make budget` generates the accuracy-budget table.

## M2.5 — Build the first complete demo

- [x] Define the supported CAD layer mapping and door-block conventions.
- [x] Implement DXF import for walls, openings, rooms, and text into `BuildingModel`.
- [x] Add unit and geometry round-trip tests for DXF input.
- [x] Connect DXF import → compliance → reports and exports through a runnable entry point.
- [x] Select a PDF library and record its licence; obtain approval before adding a copyleft dependency.
- [x] Implement vector-PDF path/text extraction and plot-scale handling.
- [x] Route DXF, vector PDF, and raster inputs to the appropriate paths.
- [x] Extract candidate site addresses from title-block text and connect the local jurisdiction proposal/confirmation flow (vector PDF/DXF; OCR pending).
- [ ] Author draws the CAD test plans and seeded violations described in specification §7.3, including registration fiducials for scans.
- [ ] Store expected outcomes per element and per rule in `eval/compliance/expected.yaml`.
- [ ] Reproduce expected verdicts from both DXF and vector-PDF inputs.

The supported semantic DXF/tagged-PDF convention and synthetic demo reproduce every draft expected verdict; ordinary untagged CAD plots and the independent author-drawn set remain outstanding. Raster routing explicitly reports the unimplemented extraction path. See [exact-input demo](docs/exact-input-demo.md). Native PDF assessment reports and external viewer acceptance are also pending.

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
- [x] Add local source-drawing/project persistence, project revisions and run snapshots for supported exact inputs. Reopening restores settings, evidence, drawings and current results; changing check inputs or drawings invalidates previous results.
- [ ] Add production database persistence and editable building-model versions.
- [x] Implement local upload/text extraction, project listing/saving, explicit ADA reference check-run and export-download endpoints.
- [x] Verify source hashes before checking, retain saved settings and engine/rule provenance, reject stale revisions/downloads, and remove partial outputs after failed runs.
- [ ] Add asynchronous processing/status endpoints and the production API lifecycle; current local runs are synchronous.
- [ ] Add the API service to the development stack; implement `make api` and `make up`.
- [ ] Generate end-to-end metrics with confidence intervals, false passes/fails, and risk–coverage curves, broken out by ruleset and input path.

**Done when:** the seeded-set end-to-end report meets M6's evaluation requirements.

## M7 — Build the web editor and 3D viewer

- [x] Record each plan's country, region and responsible authority through manual webpage entry or an explicitly confirmed drawing-text proposal. Selection is per project; verified legal authority/adoption resolution and local-code execution remain pending.
- [ ] Extend the implemented vector-text location proposal flow to OCR/raster evidence. Preserve source-page/position evidence and manual fallback; a mailing city alone must not establish the authority.
- [x] Extract labelled location hints from ordinary vector-text PDF and DXF with page/layout, fragment anchors, raw-text evidence, duplicate/conflict handling, and saved-run persistence. These remain unconfirmed; see [location evidence](docs/location-evidence.md). Offline named-authority matching and a local confirmation webpage are implemented; OCR remains pending.
- [x] Present country, state/region, city/municipality or special planning authority, and permit application date in the local upload/project-settings flow. Allow upload/draft saving before completion, but keep local-code checking unresolved until required inputs are supplied. Do not silently default to Maharashtra or infer confirmation from drawing text.
- [x] Add local upload, processing feedback, project settings, and jurisdiction confirmation (synchronous exact-input runs; production/background processing remains pending).
- [x] Add a per-project jurisdiction selector with country and state/region, including **India → Maharashtra**, followed by city/municipality or special planning authority and permit application date.
- [x] Save the selection with the project and restore it when reopened; changing it invalidates earlier check results and requires a new run (local JSON persistence; production database pending).
- [x] Add the ruleset-availability panel for recorded code editions, effective dates and source links, with adoption-chain completeness and permit-date checks. Unverified locations can be saved and local code remains **not checked**. No active verified adoption records are present; production local-rule availability remains unverified.
- [x] For Maharashtra, use manual authority selection until an India-capable resolver is implemented; do not send Indian addresses to the U.S. Census resolver. Offer ADA only as an explicitly selected reference comparison for Indian projects.
- [ ] Overlay extracted geometry on the source drawing with layer toggles.
- [x] Add optional facility type, occupancy, work type, sprinkler status and manual PDF scale entry to saved check inputs. Missing facts stay unknown; a manual scale must agree with embedded scale on supported tagged PDFs.
- [ ] Support wall/opening and label edits, plus scale recovery/manual calibration for ordinary or raster drawings.
- [ ] Rank the review queue by whether uncertainty can change a verdict; re-run checks after corrections.
- [x] Run ADA reference comparisons from the webpage only after explicit selection and saved location confirmation, using supported semantic DXF/tagged PDF. Unsupported geometry and image-only inputs produce errors without guessed verdicts.
- [x] Add findings, citations, measurements/uncertainties, governing requirements, comparison limits and coverage panels for these reference runs; local-code execution remains pending.
- [ ] Load glTF in the 3D viewer and verify scale and orientation.
- [x] Add DXF, IFC, GLB, BCF, saved run JSON and HTML/Markdown report downloads, with the persistent design-assist disclaimer and stale-download blocking.
- [ ] Add native PDF assessment-report downloads.
- [x] Implement `make web` for the local confirmation and exact-input reference-check flow.
- [x] Verify local HTTP upload/save/run/download behavior, source replacement/settings invalidation and unsupported-input handling with automated tests; perform an initial Chrome rendering smoke check.
- [ ] Complete browser interaction testing and record the full editor/review/3D/export demo.

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

- Initial region selected: Maharashtra, India. The application user selects the city/municipality or special planning authority and permit date per project; verified adoption/rule information is still needed before local checks can run.
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
