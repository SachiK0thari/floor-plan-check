# PlanCheck — Implementation Checklist

Floor plan → structured building model → accessibility and building code checks, delivered as a web application.

PlanCheck is a **design-assist tool, not a code review**. The full requirements and acceptance criteria are in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md). This file tracks implementation progress and the remaining work in small steps.

Updated on November 22, 2026. Work through the milestones in order and meet each milestone's acceptance criteria before moving on. A checked task means implementation exists; it does not imply the whole milestone is accepted.

## Product direction

Items 1 to 4 were decided by the author on November 12, 2026. [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) §1, §2, §3.2, §12, §13, §15 and §16 were updated to match on the same day; M10's detailed requirements are still to be added to the specification before M10 starts. Items 5 and 6 were decided on November 22, 2026; the specification has not yet been updated for them.

1. **PlanCheck is a web application.** The user-facing product is the webpage: upload a plan, confirm where the building is, review findings, correct the model, and export. The Python package, command-line entry points and local JSON persistence are the engine and development scaffolding behind it, not a separate product.
2. **The jurisdiction comes from the building's location, and no region is special.** The application works out the local jurisdiction in this order:
   1. **From the uploaded plan.** A site plan or title block usually carries the location. The application extracts it, proposes the responsible authority with the supporting evidence, and the user confirms or corrects it.
   2. **From the user.** When the plan has no usable location, or the evidence is ambiguous or conflicting, the application asks the user where the building is and identifies the jurisdiction from that answer. The user should not need to know the name of the authority.

   Maharashtra is only an unverified scaffold created during development. It is not the default, not the required first jurisdiction, and not a limit on where a project can be. A location whose authority has no verified ruleset is saved and reported as "local code not checked".
3. **Future: traditional design guidance.** After the regulatory checks are complete, the same building model will be checked against **Indian Vastu Shastra** and **Chinese Feng Shui** as optional, separately labelled guidance layers. These are not codes and never affect a regulatory verdict; see M10.
4. **The user chooses what to check from a top bar of three tabs inside each project.** On phone width the tabs collapse into a burger menu with the same three entries. The options are:
   - **Building code** — accessibility and building-code checks, including the local jurisdiction's adopted code. The location and jurisdiction steps belong to this option only.
   - **Vastu Shastra**
   - **Feng Shui**

   Each option has its own inputs, run, results view and report section. Each tab shows its own status: not started, needs input, results ready, or out of date. A project can hold results for more than one option, but they are never merged into one verdict. Nothing runs until the user starts it from that option's tab.
5. **Scope for now: India and the USA.** Location lookup, the country list, code families and test data are built for these two countries only. Item 2 still holds within them: no state, city or authority is a default. Where this file or the specification says "any country", read it as India or the USA until the author widens the scope.
6. **Life safety plan.** The application can make a draft life safety plan from the building model: occupant loads, exits, egress paths with travel distance, common path of travel, dead ends, exit separation and exit capacity, drawn as a sheet with tables. Making comes first. Checking the same quantities against the adopted code follows, and uses author-verified values only. The result is a draft for the designer to review, not a permit-ready sheet. See M2.6.

## Current state

The project is partway through **M2: compliance on ground-truth models**. Reports, BCF, saved runs, multi-code handling, analytic validation, and a preliminary synthetic accuracy budget are implemented. A restricted exact-input demo now runs from semantic DXF and tagged vector PDF through checks and exports. The local webpage also saves source drawings and project revisions, runs explicitly selected ADA reference comparisons, and presents findings and downloads; OCR and local-code execution from the webpage remain pending. Author hand-checks, verified local rules, and the independent CAD evaluation set remain acceptance gaps; the synthetic demo does not close M2/M2.5.

Latest local validation: 534 tests passed, including the jurisdiction-independence tests and real semantic DXF/tagged-PDF runs and HTTP upload → check → download → stale-result rejection. Type checking, lint and formatting checks for changed Python files, and JavaScript syntax checks passed. A headless Chrome smoke check verified page/JavaScript loading and the initial disabled run button; the initial rendered layout was inspected. Lint and tests pass in CI; full browser interaction testing remains unverified. Earlier rule validation verified all seven ADA rule files against the stored source text.

A full code review on November 22, 2026 found defects that can produce an unjustified `pass` or a false `fail`, and gaps that block M2.5. The resulting tasks are marked **(review)** in the milestones below, each with its item number from the review. The reproduction notes and the design for each fix are in the local working file `miscellaneous/IMPROVEMENT_PLAN.md`, which is not in Git. On the same day a second model re-checked the seven ADA rules against the stored text: values, units, sections and quotes were confirmed, one discrepancy is open, and the rules are still not author-verified. See [rule verification](docs/rule_verification.md).

## Milestone status

- [x] M0 — Repository setup: lint and tests pass in CI on Python 3.11 and 3.12 (PR #1).
- [ ] M1 — Building model, exporters, and synthetic plans: implemented; external and visual validation remain.
- [ ] M2 — Compliance engine: partly implemented; remaining tasks below.
- [ ] M2.5 — Exact DXF/tagged-PDF paths and synthetic demo implemented; independent CAD-drawn test set and acceptance remain.
- [ ] M2.6 — Life safety plan on exact inputs: not started. The travel-distance method is prototyped outside the repository.
- [ ] M3 — Segmentation model.
- [ ] M4 — Vectorization, openings, and rooms.
- [ ] M5 — OCR and scale recovery.
- [ ] M6 — Local exact-input web endpoints, source/project persistence and run revisions implemented; raster integration, production API/database and end-to-end evaluation remain.
- [ ] M7 — Local jurisdiction confirmation, ADA reference runs, findings and downloads implemented; location-first jurisdiction flow, geometry editor, review queue, 3D viewer and complete demo remain.
- [ ] M8 — LLM explanations, Q&A, rule drafting, and baselines.
- [ ] M9 — Results, demo, and write-up.
- [ ] M10 — Future: Vastu Shastra and Feng Shui guidance layers. Not started; begins after M9.

## Safety net — do before the review fixes

These protect every later change, so they come first. (review, phase 0)

- [ ] Run CI on every branch push, not only on `main` and pull requests. (E1)
- [ ] Add Python 3.13 to the CI matrix; it is the version used for development. (E2)
- [ ] Run `make validate-rules`, `make eval` and a JavaScript syntax check in CI. (E3)
- [ ] Add a coverage gate at 90% with `pytest-cov`, once the author approves the dependency. Coverage was 92% at the review. (E4)
- [ ] Add property tests that every verdict is unchanged when the model is translated, rotated or mirrored. Write them first and confirm they fail on a rotated T-shaped room before the fix in M2 step 9. (E5)

## M0 — Finish repository setup

- [x] Add the Python package, dependency lockfile, development tools, Make targets, and CI workflow.
- [x] Pass lint, formatting, type checking, and tests locally.
- [x] Create this `PRD.md` checklist to satisfy the README and specification references.
- [x] Review and commit the project files, which appeared untracked during the review.
- [x] Configure a GitHub remote and push the repository.
- [x] Confirm `make lint` and `make test` pass in CI on the configured Python versions (PR #1, Python 3.11 and 3.12, November 12, 2026). Earlier CI runs failed because a global `*.txt` ignore had kept the ADA source snapshot out of Git; it is now committed (U.S. government work, marked storable) and a fresh clone passes locally.

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
   - [ ] Author selects the jurisdiction and verifies its adoption chain, code editions, dates, and official sources. Any single authority qualifies, in any country; choose the one whose official sources the author can verify most reliably.
   - [ ] Complete its adoption records and source-storage permissions.
   - [ ] Scaffold the initial local rules with null numeric parameters.
   - [ ] Author fills and verifies the parameters; aim for the specification's initial 5–8 rules expressible by the check types.
   - [ ] Add any check types required by those rules, with known-answer tests.
   - [ ] Test local-code findings and cases where local requirements differ from ADA or an amended base rule.
   - [x] Keep the engine independent of the chosen jurisdiction: adding a second authority must need only a new adoption record and ruleset, with no code change. Tested with synthetic U.S. and New Zealand authorities added only as data (`tests/test_jurisdiction_independence.py`).
   - A region scaffold and one null-parameter draft exist for Maharashtra as a development example only. It is not the required first jurisdiction; if the author verifies a different authority first, the scaffold stays inactive. Should Maharashtra be pursued, the municipality/special authority and permit-date range are still needed; see [verification checklist](docs/maharashtra-verification.md). Synthetic multi-code tests do not establish real local requirements.

8. **Generate the accuracy budget.**
   - [x] Implement geometry perturbation and sensitivity analysis on ground-truth models.
   - [x] Generate per-check error budgets and input-resolution requirements.
   - [x] Implement `make budget` and generate the budget table under `eval/reports/`.
   - Scope: preliminary synthetic, fixture-conditioned budgets with confidence intervals. Independent author-reviewed/local-code validation remains required before treating these as production extraction or upload thresholds.

9. **Close the verdict defects found in the November 22 review.** (review, phase 1)
   - [ ] Each check declares in code its element, what it can prove, its parameters and its exceptions. The rule loader rejects a rule file that claims more than the check can prove, or that misnames a check, parameter or filter key, and `make validate-rules` reports it. Today `proves: both` in a rule file makes a fail-only check return `pass`. (A1, A6)
   - [ ] A plan with no identified entrance returns `unknown` for the entrance obligation, not a pass of "0 of 0". (A3)
   - [ ] Decide the deep-opening exception through `verdict.py`, using the wall thickness with its uncertainty; return `borderline` when the two limits disagree. (A2)
   - [ ] Include scale uncertainty in turning space and door maneuvering through one shared helper. An unset scale uncertainty returns `unknown`. Regenerate the accuracy budget afterwards. (A4)
   - [ ] Test the T-shaped turning space in the room's own wall directions, so a rotated building gets the same verdict. (A5)
   - [ ] A check that raises an error does not abort the run; the error is reported in coverage. (B1)
   - [ ] Resolve the open discrepancy in the door maneuvering rule: a front-approach failure is reported as proof, although the side-approach rows of the table need less clearance. See [rule verification](docs/rule_verification.md).
   - [ ] Add the rule statuses `draft`, `machine_checked` and `author_verified`. The author checks the seven ADA rules against the source and signs them. (F1)

10. **Prepare rules and jurisdictions for real local codes.** (review, phase 2)
    - [ ] Let an adoption record hold successive adoptions with dates, selected by the permit date. (C1)
    - [ ] Make the regime a declared property of each ruleset, in place of the literal name `ada_2010`. (C2)
    - [ ] Limit the country list to India and the USA in one checked-in table; remove hard-coded regions from the page and the proposal code. (C3)
    - [ ] Give coverage a typed schema, and split `engine.run` into planning, scoping, technical and roll-up steps with no change in behaviour. (C4, C5)
    - [ ] Require an explicit ruleset on the command line and remove the ADA fallback. (F3)

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
- [ ] Identify the site-plan sheet and title block in a multi-sheet upload, and search them first for location evidence.
- [ ] Extract the north arrow and plot boundary from exact inputs where drawn, with provenance and uncertainty; record orientation as unknown when absent. The location flow uses the site plan, and M10 depends on orientation.
- [ ] Add a DXF importer for a convention a person can draw in ordinary CAD: walls, door blocks with attributes, glazing, room labels, fixtures and corridor centrelines on named layers, with rooms and connectivity derived from the walls. The current importer reads only PlanCheck's own exports, so the author-drawn test set cannot be imported without it. Document the convention in `docs/cad-convention.md` with a template drawing; the author approves it first. (review, D1)
- [ ] Decide whether the PDF requirement for this milestone is limited to tagged PDFs, leaving ordinary vector PDFs to plan parsing. (review, D1; author decision)
- [ ] A malformed tagged drawing produces a clear error, not a `KeyError`. (review, B2)
- [ ] IFC GlobalIds and BCF topic ids are unique to each project and stable across runs. (review, B5, B6)
- [ ] Author draws the CAD test plans and seeded violations described in specification §7.3, including registration fiducials for scans. Include at least one sheet set with a site plan carrying a location, and one with no location. Include the egress cases M2.6 needs.
- [ ] Store expected outcomes per element and per rule in `eval/compliance/expected.yaml`.
- [ ] Reproduce expected verdicts from both DXF and vector-PDF inputs.

The supported semantic DXF/tagged-PDF convention and synthetic demo reproduce every draft expected verdict; ordinary untagged CAD plots and the independent author-drawn set remain outstanding. Raster routing explicitly reports the unimplemented extraction path. See [exact-input demo](docs/exact-input-demo.md). Native PDF assessment reports and external viewer acceptance are also pending.

**Done when:** the seeded set runs end to end from both exact input paths with every expected verdict reproduced.

## M2.6 — Make a life safety plan on exact inputs

Makes a draft life safety plan for one floor from the building model. It needs M2 steps 9 and 10 and the drawable CAD convention from M2.5. The design, the prototype results and the test cases are in Part G of the local working file `miscellaneous/IMPROVEMENT_PLAN.md`.

1. **Specification and inputs.**
   - [ ] Add this milestone's requirements and acceptance criteria to the specification before implementation, and update §9.6 to the exact shortest-path method.
   - [ ] Model version 2, with migration of saved models and runs: an exit designation on openings, room function in use, and an optional declared occupant load per room.
   - [ ] Propose every exterior door as an exit for the user to confirm. Until exits are confirmed, measurements are shown and every verdict that depends on exits is `unknown`.
   - [ ] Add `configs/space_functions.yaml` and propose a function from each room label; the author approves the list. A room with no function has an `unknown` occupant load.

2. **Walking distance.**
   - [ ] Add `plancheck/egress/`: the walkable space, a visibility graph over wall corners, the distance to the nearest exit from any point, the most remote point of each room to 1 mm, and the path as a polyline.
   - [ ] Report the shortest distance and the right-angle distance, with uncertainty that includes scale. A wall-clearance offset is a rule value and stays null until verified.
   - [ ] Known-answer tests on the four prototype shapes at three rotations, within 1 mm. Property tests: rigid motion does not change the distance, adding an exit never increases it, adding a wall never decreases it.
   - [ ] Meet a time budget of 2 s for a 30-room floor.

3. **Occupant load.**
   - [ ] Extend the rule format with area, per-person and count units, and with tables keyed by conditions such as room function, occupancy and sprinkler status. A lookup that matches no row returns `unknown`.
   - [ ] Compute the occupant load per room from gross or net area as the table states, with uncertainty and the rounding the rule states. Without a verified table, show areas and declared loads only.

4. **Egress network.**
   - [ ] Build one network per floor from rooms, corridor centrelines, doors and exits.
   - [ ] Measure common path of travel, dead-end corridor length and the occupant load through each door and exit. The load assignment method is the author's choice and is printed on the sheet.
   - [ ] Measure the number of exits reachable by separate routes, exit separation against the diagonal of the area served, and exit capacity from door clear widths.

5. **The sheet.**
   - [ ] Return the analysis as typed results, store it in the saved run, and add what could not be computed to coverage.
   - [ ] Draw the sheet as SVG: room load tags, exits, paths with lengths, the remote point, common paths, dead ends and separation lines, with the load schedule, the egress summary, a legend, the list of things not shown, and the disclaimer. Meaning is carried by line style and text, not colour alone.
   - [ ] Write the same content to DXF on its own layers, and add it to the HTML report.
   - [ ] Add a runnable entry point that goes from a drawn DXF to the sheet.

6. **Evaluation.**
   - [ ] The author measures travel distance, common path and dead-end length by hand on the egress cases of the CAD test set and records them with tolerances in `eval/egress/expected.yaml`; `make eval` compares.
   - [ ] Add the egress quantities to the accuracy budget.

**Done when:** for every egress case in the author-drawn set, the sheet is produced from the exact input path, every hand-measured value is reproduced within its tolerance, no verdict appears without a verified ruleset, and the known-answer and property tests pass.

### Stage 2 — check the plan against the adopted code

This stage waits on author-verified values and does not block M3.

- [ ] Author selects one US authority and one Indian authority, and verifies each one's adoption record, code edition and dates from official sources.
- [ ] Scaffold the egress rule files with null values. The author fills them from their own copy of the adopted code. No code text is stored; each rule keeps the section number, an author-written paraphrase and a link.
- [ ] Register the checks for travel distance, common path, dead-end length, exit count, exit separation and egress capacity, each declaring what it can prove. Generate boundary tests from the rule values.
- [ ] Show the findings on the sheet and in reports as building-code findings, provisional until the jurisdiction is confirmed and never merged with ADA findings.

### Later stages

- [ ] More than one floor: stairs, storeys, loads arriving from other floors, and rated walls shown on the sheet.
- [ ] Audit a life safety sheet drawn by someone else, after plan parsing (M3 to M5).

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
- [ ] Read location text, the north arrow and the plot boundary from scanned site plans and title blocks, feeding the same proposal flow as vector text.
- [ ] Report label accuracy and scale error by evidence type.

**Done when:** measured scale and label performance are reported, and missing dimensions lead cleanly to manual scale entry.

## M6 — Integrate the pipeline, API, and database

- [ ] Connect raster preprocessing, extraction, OCR, scale, and compliance.
- [ ] Preserve uncertainty through extraction and verdicts.
- [x] Add local source-drawing/project persistence, project revisions and run snapshots for supported exact inputs. Reopening restores settings, evidence, drawings and current results; changing check inputs or drawings invalidates previous results.
- [ ] Add production database persistence and editable building-model versions.
- [x] Put location-to-authority resolution behind one country-agnostic interface with a provider per country (`LocationProvider`, `resolve_address`, `providers.py`). The U.S. Census provider exists; each further provider needs an author-approved data source, licence and privacy review. A country with no provider falls back to the user naming the authority. Not yet wired to the webpage (M7).
- [x] Finish generalizing adoption-record and persistence identifiers beyond Census level/GEOID, so an authority in any country is stored and matched the same way. Records match on `country` + `authority_id`; a U.S. `geoid` is one form of it. Loading rejects duplicate authorities and cross-country chains. Saved projects store country and authority name, not Census identifiers.
- [x] Implement local upload/text extraction, project listing/saving, explicit ADA reference check-run and export-download endpoints.
- [x] Verify source hashes before checking, retain saved settings and engine/rule provenance, reject stale revisions/downloads, and remove partial outputs after failed runs.
- [ ] Add asynchronous processing/status endpoints and the production API lifecycle; current local runs are synchronous.
- [ ] An installed copy of the package runs: ship the rules, configs and web files, resolve data paths in one module, and accept `--host`, `--port` and `--data-dir`. (review, B9)
- [ ] Choose the API framework and move the local server to it behind a `ProjectStore` interface; FastAPI with uvicorn is recommended, with licences logged before adding. (review, D3; author decision)
- [ ] In that server: version project files and migrate them, so one unreadable project does not empty the list; return server faults as 500 with a logged reference, not as 400; stream uploads, validate them before storing and clean up afterwards; handle concurrent requests and recover runs left in "processing". (review, B3, B4, B7, B8)
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
- [ ] Add a top bar inside each project with three tabs: **Building code**, **Vastu Shastra** and **Feng Shui**. It is visible on every project screen and shows which tab is open. Save each option's state with the project.
- [ ] Show each tab's status: not started, needs input, results ready, or out of date. Changing the drawing or that option's inputs marks only that tab out of date.
- [ ] On phone width, collapse the tabs into a burger menu with the same three entries and statuses.
- [ ] Give each option its own inputs, run action, results view and downloads. Move the existing location, jurisdiction, ADA reference and findings screens under **Building code**.
- [ ] Until M10 delivers them, show the **Vastu Shastra** and **Feng Shui** tabs as not yet available. Selecting one explains that, and must never produce a result or fall back to building-code findings.
- [ ] Test the tabs and the phone-width burger menu with keyboard and screen-reader navigation.
- [ ] Within **Building code**, make location the first step after upload. Show what the plan says about the site, with the evidence highlighted on the sheet, and propose the responsible authority for confirmation.
- [ ] When the plan gives no usable location, ask the user where the building is: an address, a city/region/country, or a point on a map. Resolve the authority from that answer; ask for the authority by name only when resolution fails.
- [ ] Show the resolved authority chain, how it was derived (plan evidence, user location, or user-named authority) and whether a verified ruleset exists. Record the path in `jurisdiction_source`; results stay provisional until the user confirms.
- [ ] Drive the country/region/authority choices from the adoption-record catalogue so no region is hard-coded in the page. Remove Maharashtra-specific wording and behaviour from the interface, tests and docs; keep it only as one catalogue entry.
- [ ] Send a location to an external geocoder only on an explicit user action, naming the service that will receive it. Extraction alone sends nothing.
- [ ] For a location with no verified ruleset, save the project, report "local code not checked", and offer only explicitly selected reference comparisons.
- [ ] Overlay extracted geometry on the source drawing with layer toggles.
- [ ] Draw the plan with each finding's evidence as SVG, rebuild the HTML report as tables, and show the drawing beside the findings on the page. (review, D2)
- [ ] Have every check return all the measurements it makes, for the drawing and the review queue. (review, C6)
- [ ] Replace the `jurisdiction_source` values with plan evidence, user location and user-named, plus a separate confirmed flag, and set the jurisdiction from the web flow so local rules can run from the page. (review, D5)
- [ ] Choose the front-end structure; React with TypeScript, Vite and Playwright is recommended. Whatever is chosen, warn before discarding unsaved edits on a project switch, and show non-JSON error responses correctly. (review, D4; author decision)
- [ ] Add the life safety view from M2.6: confirm exits, confirm room functions and declared loads, run, review the sheet beside its tables, and download SVG and DXF. Changing the drawing or these inputs marks the result out of date. The recommended place is inside **Building code**; the author decides between that and a fourth tab.
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

**Done when:** a user can upload, open the **Building code** tab, confirm a jurisdiction derived from the plan or from a location they enter, clear the review queue, re-check, view in 3D, and export.

## M8 — Add explanations, Q&A, and baselines

- [ ] Implement section-aware ingestion of ADA and explicitly permitted local text.
- [ ] Implement deterministic section lookup for explanations and filtered retrieval for Q&A.
- [ ] Validate citations, numeric slots, code editions, and jurisdiction boundaries.
- [ ] Add human-reviewed rule drafting and adversarial drawing-text tests.
- [ ] Add optional LLM-assisted location extraction for site plans and title blocks the labelled-text extractor cannot read. The model only proposes; every proposed field must point to text found on the sheet, the user confirms it, and it never establishes the authority, edition or dates.
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

## M10 — Future: Vastu Shastra and Feng Shui guidance

Starts after M9. These layers reuse the building model, check engine, reports and webpage, but they are traditional design guidance, not law. Each runs only when the user starts it from its own tab, and neither needs a jurisdiction.

1. **Sources and scope.**
   - [ ] Author selects the source texts and the school or tradition for each system, and records them in `docs/code_sources.md` with storage permissions. Schools within each system disagree, so every ruleset names its system, school and source.
   - [ ] Author chooses an initial set of rules per system that the plan geometry can express; scaffold them with null parameters for the author to fill and verify against the chosen source.
   - [ ] Add this milestone's requirements and acceptance criteria to the specification before implementation.

2. **Keep guidance separate from regulation.**
   - [ ] Add a guidance regime alongside the ADA and adopted-code regimes. Guidance findings never enter the governing requirement, never change a regulatory verdict, and are worded as alignment with a tradition, not as compliance or violation.
   - [ ] Confirm rule files, saved runs, reports and BCF carry the new regime without changing existing regulatory results; replay earlier saved runs to prove it.

3. **Model inputs these systems need.**
   - [ ] True north and building orientation with uncertainty, from the M2.5/M5 north-arrow extraction or user entry.
   - [ ] Plot boundary, main entrance, and room functions beyond the current room types (for example kitchen, bedroom, prayer room, toilet, staircase).
   - [ ] Any non-drawing inputs the chosen schools require, entered by the user and left unknown otherwise. Missing inputs return `unknown`, as for regulatory checks.

4. **Check types.**
   - [ ] Directional zone of a room or element relative to the plan or plot, on the grid the chosen school defines.
   - [ ] Facing direction of the main entrance and of selected rooms.
   - [ ] Relative placement and alignment between elements, as the chosen rules require.
   - [ ] Known-answer, rotation and mirror tests for each; orientation uncertainty must be able to produce `unknown` near a zone boundary.

5. **Web application.**
   - [ ] Enable the **Vastu Shastra** and **Feng Shui** tabs added in M7, each opening its own flow: confirm orientation and room functions, choose the school, run, and review.
   - [ ] Save the chosen school and inputs with the project; changing them invalidates that option's earlier results only, leaving building-code results untouched.
   - [ ] Give each option its own results view and report section with its own citations and disclaimer, visually distinct from building-code findings.
   - [ ] Extend M8 explanations to guidance rules, with citations limited to the selected system and school.

**Done when:** a user can open the Vastu Shastra or Feng Shui tab for a project and receive cited, separately labelled findings from author-verified rules, with regulatory results unchanged.

## Author inputs needed

- The first authority to verify, which can be anywhere; Maharashtra is one option, not a commitment. Verified adoption and rule information is needed before local checks can run for any location.
- For each country beyond the U.S. where location lookup should work: an approved geocoding or boundary data source, its licence, and agreement to send addresses to it.
- For M10: the Vastu and Feng Shui source texts and schools to follow, and the verified rule parameters.
- Door clear-width deduction values and uncertainties, supported by door/frame details. Until supplied, use measured clear widths or report `unknown`.
- Independently hand-checked plans and the CAD-drawn evaluation set.
- PDF-library licensing decision before adding a copyleft dependency.
- Dataset access/licence confirmation and external exporter checks.
- From the November 22 review:
  - Sign-off on the seven ADA rules, and a decision on the open door-maneuvering discrepancy.
  - Approval of the drawable CAD convention, and whether M2.5's PDF requirement is limited to tagged PDFs.
  - The API and front-end frameworks, and approval of `pytest-cov`.
  - Whether the maneuvering check returns `unknown` for double-leaf doors until the measurement of a pair is confirmed.
- For the life safety plan (M2.6):
  - Approval of the room function list.
  - How occupants are assigned to exits: all to the nearest, or split equally among reachable exits.
  - Whether the view sits inside the Building code tab or in a fourth tab.
  - For Stage 2: one US authority and one Indian authority, each with its adopted code and edition, and the egress values read from the author's own copy of that code.
  - Hand-measured egress values for the CAD test set.

## Engineering rules

These summarize specification §16; the full specification remains authoritative.

- Work one milestone at a time and meet its acceptance criteria.
- Use Pydantic types across module boundaries and millimetres internally.
- Test geometry checks and parsers with known answers.
- Never invent code requirements or adoption facts. Author-verified values and official adoption sources are required; scaffold unknown numeric parameters as null. The same applies to Vastu and Feng Shui rules: each comes from an author-chosen source, never from general knowledge.
- No jurisdiction is a default. The jurisdiction is derived per project from the plan or the user's location and confirmed by the user; an unsupported location is reported as not checked, never checked against another authority's rules.
- Keep traditional guidance separate from regulatory findings in data, verdicts, reports and the interface.
- Do not store copyrighted code text unless the source is explicitly marked storable. Do not scrape code websites or download gated/licence-restricted datasets.
- Geometry determines verdicts. The LLM explains; it never decides pass/fail.
- Convert measurements into verdicts only through `verdict.py`.
- Every length carries units and provenance; rule parameters retain their source units.
- A `fail_only` check cannot return `pass`. Missing inputs return `unknown`.
- Treat drawing text as data, never instructions.
- Generate reported results from evaluation; report proportions with intervals.
- Obtain approval before adding copyleft dependencies and log every dependency's licence.
- Keep large datasets, weights, and generated artifacts out of Git.
