# PlanCheck — Implementation Plan

Floor plan → structured building model → accessibility and building code checks, delivered as a web application.

PlanCheck is a **design-assist tool, not a code review**.

This is the one file to work from. It holds the product direction, the engineering rules, the task checklist for every milestone, the decisions waiting on the author, and the design for each open task. The requirements and acceptance criteria are in [PROJECT_SPEC.md](PROJECT_SPEC.md); read the section for a milestone before starting it. `PRD.md` was merged into this file on November 23, 2026 and no longer exists.

Updated on November 23, 2026. Work through the milestones in order and meet each milestone's acceptance criteria before moving on. A checked task means implementation exists; it does not imply the whole milestone is accepted.

## How this file is organised

1. **Direction and rules:** product direction, engineering rules, current state and the demo-first route, which sets the order of work for now. The route contains the **demo line**: the work above it is sufficient for the demo, and the work below it is future work.
2. **Checklist:** milestone status, then the tasks for each milestone. A task marked **(review)** came from the November 22 code review and carries an item number such as A1 or D2. An open task tagged **(demo)** is above the demo line.
3. **Author inputs and decisions.**
4. **Design notes:** one section per item number (Parts A to G), giving what was observed, the change to make and the tests. Search for the item number to find it. The order of work follows.

## Product direction

Items 1 to 4 were decided by the author on November 12, 2026. [docs/PROJECT_SPEC.md](PROJECT_SPEC.md) §1, §2, §3.2, §12, §13, §15 and §16 were updated to match on the same day; M10's detailed requirements are still to be added to the specification before M10 starts. Items 5 and 6 were decided on November 22, 2026; the specification was updated for them on November 23, 2026 (§1, §2, §3.2, §5, §6, §7.3, §9.3, §9.6, §9.7, §9.8, §12, §13, §15, §16 and §17).

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
7. **Show something soon.** Decided on November 23, 2026. The audience is recruiters and hiring managers, through a short demo video and the repository itself. Until the demo is recorded, work follows the demo-first route below, not the milestone order. The route's demo line separates the work that is sufficient for the demo from the future work.

## Engineering rules

These summarize specification §16; the full specification remains authoritative.

- Work one milestone at a time and meet its acceptance criteria.
- Use Pydantic types across module boundaries and millimetres internally.
- Test geometry checks and parsers with known answers.
- Never invent code requirements or adoption facts. Author-verified values and official adoption sources are required; scaffold unknown numeric parameters as null. The same applies to Vastu and Feng Shui rules: each comes from an author-chosen source, never from general knowledge.
- The scope for now is India and the USA. Build location lookup, the country list, code families and test data for these two only, and keep the interfaces country-agnostic.
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

## Current state

The project is partway through **M2: compliance on ground-truth models**. Reports, BCF, saved runs, multi-code handling, analytic validation, and a preliminary synthetic accuracy budget are implemented. A restricted exact-input demo now runs from semantic DXF and tagged vector PDF through checks and exports. The local webpage also saves source drawings and project revisions, runs explicitly selected ADA reference comparisons, and presents findings and downloads; OCR and local-code execution from the webpage remain pending. Author hand-checks, verified local rules, and the independent CAD evaluation set remain acceptance gaps; the synthetic demo does not close M2/M2.5.

Latest local validation (November 25, 2026): 653 tests passed with 91.6% line and branch coverage; lint, type checking, rule validation and `make eval` (now including the injection checks) passed, after the explanation-layer measurement. Previous validation (November 24, 2026): 648 tests passed with 92.6% line and branch coverage; lint, type checking, rule validation, `make eval` and `make demo` passed, after A1, A2, A3, A6 and C6 and the CubiCasa5K conversion, training and resume scripts. Not re-checked in a browser. Previous validation (November 23, 2026): 543 tests passed with 91.9% line and branch coverage against a 90% gate; lint, type checking, rule validation, `make eval`, `make demo` and the JavaScript syntax check passed. The findings are now drawn on the plan in the HTML report and on the page; this was checked in headless Chrome on the seven-room synthetic sample, by screenshot only. Clicking through the page in a browser (selecting rows and shapes, keyboard use) has not been tested. Earlier validation: 534 tests passed, including the jurisdiction-independence tests and real semantic DXF/tagged-PDF runs and HTTP upload → check → download → stale-result rejection. Type checking, lint and formatting checks for changed Python files, and JavaScript syntax checks passed. A headless Chrome smoke check verified page/JavaScript loading and the initial disabled run button; the initial rendered layout was inspected. Lint and tests pass in CI; full browser interaction testing remains unverified. Earlier rule validation verified all seven ADA rule files against the stored source text.

A full code review on November 22, 2026 found defects that can produce an unjustified `pass` or a false `fail`, and gaps that block M2.5. The resulting tasks are marked **(review)** in the milestones below, each with its item number from the review. The reproduction notes and the design for each fix are in the design notes in the second half of this file, under the same item number. On the same day a second model re-checked the seven ADA rules against the stored text: values, units, sections and quotes were confirmed, one discrepancy is open, and the rules are still not author-verified. See [rule verification](rule_verification.md).

## Demo-first route

The author said on November 23, 2026 that the goal is to show something soon. This section is the route for that, and it sets the order of work until the demo is recorded. Where it differs from the milestone order, it wins. The engineering rules still apply, and no milestone is marked accepted because of it.

The route is split by the **demo line**, added on November 23, 2026 at the author's request. The work above the line is sufficient to record the demo. Nothing below the line starts before the recording unless the author moves it above. In the milestone checklists further down, an open task tagged **(demo)** is above the line; every other open task is below it. The stage numbers are kept from the first version of the route, so stages 1 and 4 are above the line and stages 2 and 3 are below it.

### Above the line: sufficient for the demo

**What the demo shows.** A CAD drawing is uploaded on the web page. Each accessibility finding is drawn on the plan with its measurement, its requirement and its citation. A language model then explains each finding in plain language, and code checks every citation and number in the explanation against the stored ADA text. Every number on screen comes from a run or from `eval/reports/`.

| Stage | What becomes showable | Tasks | Needed from the author |
|---|---|---|---|
| 1. Findings on the plan | The page and the HTML report draw the plan with each finding's evidence, in place of raw JSON | E1, E2, E3; D2; C6; A1, A2, A3, A6; a README screenshot | Nothing. Signing the seven ADA rules (decision 1) is recommended before recording, so the findings are not labelled unverified |
| 4. An AI component | A plain-language explanation of each finding, with its citation and numbers validated against the stored ADA text | A thin slice of M8: section lookup, explanation, citation and number validation | Nothing more to build it; decision 13 is settled. The author labels the citation sample |

**Checklist.** The demo is recorded when every line here is checked.

- [x] Stage 1: CI runs on every branch push, on Python 3.13, with the project's own gates. (E1, E2, E3)
- [x] Stage 1: the findings are drawn on the plan on the page and in the HTML report, with a seven-room sample plan and a README screenshot. (D2)
- [x] Stage 4: each finding is explained in plain language, with its citation and numbers validated.
- [x] Stage 1: each check declares what it can prove, and the rule loader rejects a rule file that claims more. (A1, A6) Done November 24, 2026.
- [x] Stage 1: the deep-opening exception is decided through `verdict.py`. (A2) Done November 24, 2026.
- [x] Stage 1: a plan with no identified entrance returns `unknown`. (A3) Done November 24, 2026.
- [x] Stage 1: every check returns all the measurements it makes, and the accessible route is drawn as a line. (C6) Done November 24, 2026.
- [ ] Stage 4: measure the explanation layer as specification §11.4 describes: the raw rejection rate by reason, citation support on a sample the author labels by hand, and the two adversarial plans. Report each proportion with its sample size and interval. Measurement built and run November 25, 2026 (`make eval-explain`); the rejection rate and the adversarial plans are measured. **Open: the author labels `eval/rag/citation_labels.yaml`**, at least items 1 to 34, then runs `make eval-explain-report`.
- [ ] Author: sign the seven ADA rules (decision 1) and settle the door maneuvering discrepancy (decision 12). Recommended, not blocking; without them the findings on screen are labelled unverified.
- [ ] Commit and push the work, and confirm the CI workflow passes on GitHub with its new steps.
- [ ] Add the measured numbers and the stated limits to the README, record the demo video and link it from the README.

**Progress on stage 4 (November 23, 2026).** Done ahead of the rest of stage 1, at the author's request. `plancheck/rag/` explains each `fail`, `borderline` and `unknown` finding through OpenRouter. The model writes a template with named slots and code fills in every value; the sources are the quotes in the finding's own rule file; a validator rejects any digit outside a slot, any section not in those sources, a list of the element slot, and wording that claims compliance. Element ids, room labels and the address are never sent, and numbers are hidden from the model. Explanations run only from an explicit button on the page or `--explain` on the command line, are stored in `explanations.json` beside the run, and appear in the HTML report and on the page labelled as written by a language model. On the seven-room sample all 18 findings were explained in 3 to 5 s with no rejection; the model's reasoning step is off in the config because, when on, it sometimes used the whole output limit and returned nothing. Not yet done: the hand-labelled citation-support sample and the adversarial plans in specification §11.4, so there is no measured rejection rate beyond that one sample.

**Progress on stage 4 (November 25, 2026): the §11.4 measurement.** `plancheck/evaluation/explain_eval.py` runs the explanation layer over 316 synthetic plans: the review fixtures, the seven-room sample, 288 one-room variants that walk each check's branches, 20 random plans and the two adversarial plans with their clean twins. That gives 1,362 findings to explain but only **34 distinct prompts**: the model is sent no number and no element id, so findings that differ only in those share a prompt, and adding more random plans stops adding prompts after about twenty. Results are in `eval/reports/explanation-eval.md`.

- **Raw rejection rate:** 0 of 34 first outputs rejected in each of three runs (Wilson 95% 0.0% to 10.2% per run). The runs repeat the same prompts, so they are not pooled.
- **Injection:** both adversarial plans carry text aimed at the model in room labels, door tags, door ids, a dimension and the site address, and go through the DXF import. The text survives the import in all five places; the verdicts match the clean twin and the prompts are byte-identical, so the model is sent nothing of it. This check needs no model call, so it now runs in `make eval` and therefore in CI. A test confirms that the check fails if drawing text stops being hidden.
- **Citation support: waiting for the author.** Specification §11.4 asks for a hand-labelled sample of 50. Here there are only 34 prompts, so the file lists the whole population instead of a sample. Temperature zero is not deterministic on this model: the three runs wrote different wording for almost every prompt, giving 100 distinct explanations. Items 1 to 34 are run 1, one per prompt; labelling those covers every prompt once, and labelling the rest narrows the interval. Each item carries the text and the stored source text of every section it cites.
- `make eval-explain` calls the model and rewrites the labels file, keeping every label already given; `make eval-explain-report` recomputes the report after labelling, without calling the model.

**Progress on stage 1 (November 23, 2026).** Done: E1, E2, E3 and D2, plus a seven-room synthetic sample plan (`sample_office_plan`, written to `out/demo/sample-office/` by `make demo`) so there is more than a one-room fixture to show. The README carries a screenshot of the page with that plan. A1, A2, A3, A6 and C6 were done on November 24, 2026, so stage 1's code tasks are complete.

Stage 1 is showable when it ends. At the sizes used in the design notes, stage 1 is about a week of work in total, and part of it is done.

**Why stage 4 is above the line.** The specification frames this project for an AI engineering role, and stages 1 to 3 contain no model. The explanation layer is the quickest AI component to build, because it works on findings and needs no extraction model. It also shows the design principle most worth showing: geometry decides, and the language model only explains.

**What the demo may claim.** Only what is measured: the test count and coverage, the expected verdicts reproduced on the fixtures from both exact input paths, and the accuracy budget. It must say that the fixtures are synthetic, that plan parsing from scans is not built, and that the rules are not author-verified until the author signs them.

---

### DEMO LINE: record the demo here

Everything above this line is sufficient for the demo. Everything below it, in this section and in the open untagged tasks of the milestone checklists, is future work and waits until the demo is recorded.

---

### Below the line: after the demo

**Target roles.** Stated by the author on November 23, 2026: applied AI and forward deployed engineer (FDE) roles, broadly. The author also wants to showcase computer vision, so the vision slice comes first and ends in a second demo recording.

**Order after the recording:**

1. **The computer vision slice:** M3 plus a rough first form of M4, so that a scanned plan goes through to a finding on a handful of plans. Report segmentation and opening metrics against the published CubiCasa baseline, calibration, and the results against the M2 accuracy budget, with failure cases. It needs the CubiCasa5K licence confirmed, the dataset path and a GPU. While it waits for those, item 2 proceeds. **Record the second demo when it is done.**
2. **Stage 3, a drawing the author made.** It shows the system working on input it did not generate, which matters most for FDE roles. About a week.
3. **The multimodal-LLM-only baseline from M8**, on the same fixtures. It answers "why not just ask the model?" with numbers.
4. **An installable, deployable service.** B9 first, then D3 and the container work in M6.
5. **Stage 2, the life safety sheet.** About a week and a half.

The author may move any of these above the line. None of them accepts a milestone.

**Exception, November 24, 2026: the computer vision slice runs in parallel with the demo work.** The author chose this when the dataset and GPU became available. Training runs on Kaggle in the background while the open demo tasks continue locally; the demo checklist above is unchanged and still decides when the first demo is recorded. Inputs settled the same day: the CubiCasa5K licence (CC BY-NC-SA 4.0, see [data sources](data_sources.md)), the copy used (the Kaggle copy, checked against the official split counts), and the GPU (Kaggle's free tier, a T4, about 30 hours a week and 12 hours per run). Paid GPUs need the author's approval for each run.

| Stage | What becomes showable | Tasks | Needed from the author |
|---|---|---|---|
| 2. Life safety sheet | Exits, the most remote point and walking paths with their lengths, with room areas and declared loads, drawn as a sheet | E5, A4, A5; then G2, G3, G8, G9 and G10, limited to travel distance and the sheet | Nothing. Occupant loads stay "declared or area only" until a verified table exists |
| 3. A drawing the author made | A plan drawn in ordinary CAD runs through stages 1 and 2 | D1, B2, B5 | Approve the CAD convention (decision 2), then draw two or three plans, not the full set of twenty |

**Deferred, in milestone order:** the rest of M2 step 10 (C1, C2, C4, C5); the full CAD test set and M2.5 acceptance; occupant load tables, common path, dead ends and exit capacity (G4 to G7) and Stage 2 checking; the rest of plan parsing (the remainder of M3 and M4, and M5); the rest of the production API and database (M6); the tab bar, geometry editor, review queue and 3D viewer (M7); the rest of M8; the independent test set (M9); and M10.

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

- [x] Run CI on every branch push, not only on `main` and pull requests. (E1)
- [x] Add Python 3.13 to the CI matrix; it is the version used for development. (E2)
- [x] Run `make validate-rules`, `make eval` and a JavaScript syntax check in CI. Changed on November 23, 2026; the workflow has not yet run on GitHub with these steps. (E1 to E3)
- [x] Add a coverage gate at 90% with `pytest-cov`. Done on November 23, 2026: `make test` measures line and branch coverage of `plancheck/` and fails under 90%; CI runs `make test`. Coverage was 91.9% when the gate was added. (E4)
- [ ] Add property tests that every verdict is unchanged when the model is translated, rotated or mirrored. Write them first and confirm they fail on a rotated T-shaped room before the fix in M2 step 9. (E5)

## M0 — Finish repository setup

- [x] Add the Python package, dependency lockfile, development tools, Make targets, and CI workflow.
- [x] Pass lint, formatting, type checking, and tests locally.
- [x] Create the implementation checklist that the README and specification refer to. It began as `PRD.md` and was merged into this file on November 23, 2026.
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
   - Supported scope: event-exact rectilinear profiles with inferred rectangular paths or supplied full-arm paths. Exception distances across bends/branches and unsupported geometry return `unknown`; see [measurement method and limits](corridor_width.md). Automatic medial-axis extraction remains future work.

2. **Close applicability and scoping gaps.**
   - [x] Review the fallback to today's date when `permit_date` is missing; require the information needed to establish applicability and report unresolved applicability explicitly.
   - [x] Report elements excluded by scoping as `not_applicable`, with the reason, rather than silently omitting them.
   - [x] Confirm missing project inputs and surfaced exceptions remain visible in results and coverage.

3. **Complete multi-code result handling.**
   - [x] Keep ADA and adopted-building-code findings separate.
   - [x] Add a derived governing requirement for applicable rules testing the same quantity on the same element.
   - [x] Test stricter local requirements, amendments, deletions, and rules with different applicability windows.
   - Governing comparisons currently support explicit scalar door-clear-width semantics. Compound checks and unresolved exceptions/applicability remain separate, with comparison omissions explained. See [multi-code results](multi_code_results.md). Local tests use synthetic adoption facts; production jurisdiction verification remains below.

4. **Make runs reproducible.**
   - [x] Record the engine version or Git SHA alongside the existing rule hashes.
   - [x] Record the dependency lockfile hash and verdict configuration.
   - [x] Include project context and the resolved ruleset list in the saved run artifact.
   - [x] Add JSON save/load round-trip and snapshot-based replay tests, preserving missing inputs, exceptions, and amendment/adoption history. See [saved check runs](check_run_artifacts.md).

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
   - [ ] Author selects the jurisdiction and verifies its adoption chain, code editions, dates, and official sources. Any single authority in India or the USA qualifies; choose the one whose official sources the author can verify most reliably.
   - [ ] Complete its adoption records and source-storage permissions.
   - [ ] Scaffold the initial local rules with null numeric parameters.
   - [ ] Author fills and verifies the parameters; aim for the specification's initial 5–8 rules expressible by the check types.
   - [ ] Add any check types required by those rules, with known-answer tests.
   - [ ] Test local-code findings and cases where local requirements differ from ADA or an amended base rule.
   - [x] Keep the engine independent of the chosen jurisdiction: adding a second authority must need only a new adoption record and ruleset, with no code change. Tested with synthetic U.S. and New Zealand authorities added only as data (`tests/test_jurisdiction_independence.py`).
   - A region scaffold and one null-parameter draft exist for Maharashtra as a development example only. It is not the required first jurisdiction; if the author verifies a different authority first, the scaffold stays inactive. Should Maharashtra be pursued, the municipality/special authority and permit-date range are still needed; see [verification checklist](maharashtra-verification.md). Synthetic multi-code tests do not establish real local requirements.

8. **Generate the accuracy budget.**
   - [x] Implement geometry perturbation and sensitivity analysis on ground-truth models.
   - [x] Generate per-check error budgets and input-resolution requirements.
   - [x] Implement `make budget` and generate the budget table under `eval/reports/`.
   - Scope: preliminary synthetic, fixture-conditioned budgets with confidence intervals. Independent author-reviewed/local-code validation remains required before treating these as production extraction or upload thresholds.

9. **Close the verdict defects found in the November 22 review.** (review, phase 1)
   - [ ] Each check declares in code its element, what it can prove, its parameters and its exceptions. The rule loader rejects a rule file that claims more than the check can prove, or that misnames a check, parameter or filter key, and `make validate-rules` reports it. Today `proves: both` in a rule file makes a fail-only check return `pass`. (A1, A6) **(demo)** Done November 24, 2026: `plancheck/compliance/contracts.py` holds `CheckSpec` and the contract checks; `CHECKS` and `SCOPING` declare each function's contract; `load_ruleset` rejects violations, `resolve` rejects an `obligated_by` id that is not a resolved scoping rule, `make validate-rules` warns on unmapped `room_type` values, and the engine bounds each verdict by the check's own capability and uses `connectivity` and `uses_check` instead of hard-coded check names.
   - [x] A plan with no identified entrance returns `unknown` for the entrance obligation, not a pass of "0 of 0". (A3) **(demo)** Done November 24, 2026: `Obligation.unresolved_reason`, set by `entrance_doors` when no exterior door or doorway is modelled.
   - [x] Decide the deep-opening exception through `verdict.py`, using the wall thickness with its uncertainty; return `borderline` when the two limits disagree. (A2) **(demo)** Done November 24, 2026, with `same_or_borderline` in `verdict.py`. With k = 2, the design note's 620 ± 20 mm row is also `borderline` (580 mm is within reach of 609.6 mm); its `fail` was the old behaviour.
   - [ ] Include scale uncertainty in turning space and door maneuvering through one shared helper. An unset scale uncertainty returns `unknown`. Wall-face uncertainties add linearly (decided November 23, 2026). Regenerate the accuracy budget afterwards. (A4)
   - [ ] Test the T-shaped turning space in the room's own wall directions, so a rotated building gets the same verdict. (A5)
   - [ ] A check that raises an error does not abort the run; the error is reported in coverage. (B1)
   - [ ] Resolve the open discrepancy in the door maneuvering rule: a front-approach failure is reported as proof, although the side-approach rows of the table need less clearance. See [rule verification](rule_verification.md).
   - [ ] Add the rule statuses `draft`, `machine_checked` and `author_verified`. The author checks the seven ADA rules against the source and signs them. (F1)

10. **Prepare rules and jurisdictions for real local codes.** (review, phase 2)
    - [ ] Let an adoption record hold successive adoptions with dates, selected by the permit date. (C1)
    - [ ] Make the regime a declared property of each ruleset, in place of the literal name `ada_2010`. (C2)
    - [ ] Limit the country list to India and the USA in one checked-in table; remove hard-coded regions from the page and the proposal code. (C3)
    - [ ] Give coverage a typed schema, and split `engine.run` into planning, scoping, technical and roll-up steps with no change in behaviour. (C4, C5)
    - [ ] Require an explicit ruleset on the command line and remove the ADA fallback. (F3)
    - [ ] Look elements up by id through dictionaries on the model, and add a per-run cache to `CheckContext` for door verdicts, the adjacency map and the wall union. Low priority for today's run times, but M2.6 reads its analysis from this cache. (C7)
    - [x] Bring the README and the specification's §5 model listing in line with the code. Done on November 23, 2026. (F2)

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

The supported semantic DXF/tagged-PDF convention and synthetic demo reproduce every draft expected verdict; ordinary untagged CAD plots and the independent author-drawn set remain outstanding. Raster routing explicitly reports the unimplemented extraction path. See [exact-input demo](exact-input-demo.md). Native PDF assessment reports and external viewer acceptance are also pending.

**Done when:** the seeded set runs end to end from both exact input paths with every expected verdict reproduced.

## M2.6 — Make a life safety plan on exact inputs

Makes a draft life safety plan for one floor from the building model. It needs M2 steps 9 and 10, the drawable CAD convention from M2.5, and the plan drawing from D2 (`plancheck/export/svg.py`). D2 is listed under M7; build its first step here if M7 has not started. The design, the prototype results and the test cases are in Part G below.

1. **Specification and inputs.**
   - [x] Add this milestone's requirements and acceptance criteria to the specification before implementation, and update §9.6 to the exact shortest-path method. Done on November 23, 2026: specification §9.6, §9.8 and M2.6 in §15.
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

- [x] Author obtains CubiCasa5K and confirms its licence and local dataset path. Done November 24, 2026: the Kaggle copy in the author's account; see [data sources](data_sources.md).
- [x] Prepare annotations and the official train/validation/test splits. `training/cubicasa_prep.py` converts every annotation into room and icon masks with the official splits, tested on hand-written SVGs. Ran on Kaggle November 24, 2026: 5,000 plans (4,200 / 400 / 400), no failures.
- [ ] Implement preprocessing while preserving image-to-model transforms.
- [ ] Train wall, door, window, and room segmentation with a junction-detection head. First model (`training/train_seg.py`, November 24, 2026): the five classes of specification §8.1 with a U-Net on a ResNet-34 encoder, 60 epochs on Kaggle (split in two by an out-of-memory stop and `--resume`). Test IoU: wall 0.792, door 0.699, window 0.788, room 0.914; results, failure cases and the comparison with the paper are in [training/README.md](../training/README.md). Still open: the junction head, and the cause of the main process growing about 0.6 GB per epoch.
- [x] Calibrate confidences on the validation split. Temperature scaling (T = 1.25): pixel-level expected calibration error on the test split 0.021 before and 0.006 after. Per-class calibration not yet measured.
- [ ] Implement `make train-seg` and report test metrics plus a reliability diagram. Test metrics and the reliability diagram are produced by the Kaggle run (`metrics.json`, `reliability.png`); `make train-seg` does not exist yet.

Against the done-when line below: wall IoU and calibration are reported against the paper, but opening metrics are pixel IoU only. The paper's instance-level opening figures need extracted openings (M4), and its class set differs from ours, so the comparison is indicative.

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
- [x] Extract labelled location hints from ordinary vector-text PDF and DXF with page/layout, fragment anchors, raw-text evidence, duplicate/conflict handling, and saved-run persistence. These remain unconfirmed; see [location evidence](location-evidence.md). Offline named-authority matching and a local confirmation webpage are implemented; OCR remains pending.
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
- [x] Draw the plan with each finding's evidence as SVG, rebuild the HTML report as tables, and show the drawing beside the findings on the page. Done on November 23, 2026 (`plancheck/export/svg.py`, `plan.svg` in every run). Selecting a row or a shape highlights the other. (review, D2)
- [ ] Write the `.md` report as Markdown tables; it is still plain text. Draw the accessible route as a line, which needs C6; until then a route finding is drawn as its room outline. The route line is done (November 24, 2026): a polyline through each door's midpoint and a point inside each room it enters. The route line is above the demo line; the Markdown tables are not. (review, D2) **(demo, in part)**
- [x] Have every check return all the measurements it makes, for the drawing and the review queue. (review, C6) **(demo)** Done November 24, 2026: `NamedMeasurement` on `CheckOutcome` and `Finding`; door maneuvering returns each depth and latch clearance it measures, turning space its circle, the corridor its minimum and each narrow run and separation; `measured` is the tightest one (`tightest`); `margin_in_sigmas` is in `verdict.py`; the report lists every measurement of a compound check. Not done: `review_ranking`, which belongs with the M7 review queue.
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
- [ ] Implement deterministic section lookup for explanations and filtered retrieval for Q&A. Explanations are done in a first form that uses the quotes in each rule file as the fetched set (`plancheck/rag/explain.py`); section lookup in the full ADA text and Q&A remain.
- [ ] Validate citations, numeric slots, code editions, and jurisdiction boundaries. Citations and numeric slots are validated for explanations; code editions and jurisdiction boundaries remain, and matter once local rules exist.
- [ ] Add human-reviewed rule drafting and adversarial drawing-text tests.
- [ ] Add optional LLM-assisted location extraction for site plans and title blocks the labelled-text extractor cannot read. The model only proposes; every proposed field must point to text found on the sheet, the user confirms it, and it never establishes the authority, edition or dates.
- [ ] Evaluate citation support, raw rejection rate, retrieval, abstention, and rule-drafting corrections. For explanations, the rejection rate, citation support and the two adversarial plans are above the demo line. **(demo, in part)**
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

## Author inputs and decisions

### Inputs only the author can supply

- The first authority to verify, which can be anywhere in India or the USA; Maharashtra is one option, not a commitment. Verified adoption and rule information is needed before local checks can run for any location.
- For India, and for any country added later: an approved geocoding or boundary data source, its licence, and agreement to send addresses to it. The U.S. Census provider exists.
- For M10: the Vastu and Feng Shui source texts and schools to follow, and the verified rule parameters.
- Door clear-width deduction values and uncertainties, supported by door/frame details. Until supplied, use measured clear widths or report `unknown`.
- Independently hand-checked plans and the CAD-drawn evaluation set, including the egress cases and their hand-measured travel distance, common path and dead-end length.
- PDF-library licensing decision before adding a copyleft dependency.
- Dataset access/licence confirmation and external exporter checks. CubiCasa5K and a GPU are needed for the computer vision slice, the first work after the demo.
- Sign-off on the seven ADA rules against the source text.
- For Stage 2 of the life safety plan: the egress values read from the author's own copy of each adopted code.

### Decisions

Each decision is described in the design notes under the item number given. Work that depends on an open decision waits for it.

1. **Rule verification (F1):** adopt the three-state status, or sign the seven ADA rules yourself. Recommended: the three-state status.
2. **CAD drawing convention (D1):** approve or change the layer and block convention, name the fixture and corridor-path layers, and decide whether to narrow M2.5's PDF requirement to tagged PDFs. Recommended: narrow it.
3. **Frameworks (D3, D4):** FastAPI with uvicorn for the API; React, TypeScript and Vite for the page; Playwright for browser tests. Each needs its licence logged.
4. **Country list (C3): settled.** A checked-in table holding India and the USA, not the LGPL `pycountry` package. Settled on November 22, 2026 by the scope decision.
5. **Uncertainty convention (A4): settled.** Wall-face uncertainties add linearly, which is the conservative form. Settled on November 23, 2026, when the author asked for the recommendation to be applied. Recorded in [corridor_width.md](corridor_width.md) and specification §9.3.
6. **Double-leaf doors:** the maneuvering check treats a `double_swing` door as a single leaf hinged at `hinge_at`, with the latch at the meeting edge. Whether that matches how the standard measures a pair is a code question that has not been answered. Until you confirm it, the safer behaviour is to return `unknown` for `double_swing` in that check.
7. **Coverage tool (E4): settled.** `pytest-cov` is a development dependency. Approved by the author on November 23, 2026.
8. **Life safety plan, placement (G10):** a view inside the Building code tab (recommended), or a fourth tab.
9. **Life safety plan, load assignment (G5):** assign each room's occupants to the nearest exit, or split them equally among reachable exits.
10. **Life safety plan, first authorities (Stage 2):** which US authority and which Indian authority to verify first, with the adopted code and edition for each.
11. **Life safety plan, space functions (G2):** approve the list of function ids in `configs/space_functions.yaml` once drafted.
12. **Door maneuvering discrepancy:** a front-approach failure is reported as proof, although the side-approach rows of the table need less clearance. Decide how the check should treat it; see [rule verification](rule_verification.md).
13. **AI component for the demo (demo-first route, stage 4): settled and built.** On November 23, 2026 the author chose OpenRouter and the model `deepseek/deepseek-v4.1-flash-1017`. The client uses the standard library, so no dependency was added. The key is `OPENROUTER_API_KEY` in `.env`; the model and service are in `configs/explain.yaml`.

---

## Design notes: the November 22 review

Reviewed on November 22, 2026, at commit `81f8556` on branch `m2-jurisdiction-independence`.

Parts A to F list defects found in a full read of the code and the design changes that upcoming milestones need. Part G is the design for the life safety plan. Every item is a task in the checklist above, under the milestone it belongs to. The engineering rules apply to every change below, in particular: never invent a code requirement or adoption fact, and only `verdict.py` turns a measurement into a verdict.

### Updates since the review

- **Scope (November 22, 2026):** the author limited the project to India and the USA for now. C3's country list is therefore a two-entry table, and decision 4 is settled in favour of the checked-in table.
- **Rule verification (F1):** a second model re-checked the seven ADA rules against the stored text on November 22, 2026. Values, units, sections and quotes were confirmed; one meaning discrepancy is open in the maneuvering-clearance rule. The record is in [docs/rule_verification.md](rule_verification.md), and each rule's `verified_by` line now says it is not author-verified. Author sign-off is still required.
- **Part G added:** making a life safety plan, requested by the author on November 22, 2026.
- **One file (November 23, 2026):** `PRD.md` was merged into this file, which lives in `docs/` and is tracked in Git. C7 and F2 were added to the checklist, and F2 was done. The uncertainty convention in A4 was settled. The coverage gate (E4) was added with the author's approval. The specification was updated for the India and USA scope and the life safety plan. C7 moved to phase 2 in the order of work, because the life safety plan needs its cache.

### How this review was done

- Read every module under `plancheck/`, both files under `web/`, the rule files, configs, CI workflow, the checklist (then `PRD.md`) and the specification.
- Ran the existing checks: 534 tests pass; `ruff check`, `ruff format --check` and `mypy` are clean.
- Measured coverage with `pytest-cov` (not a project dependency; run in a throwaway environment): 92% line and branch coverage overall.
- Reproduced each defect in Parts A and B with a short script before listing it. Each entry gives the observed result. The scripts were kept outside the repository; the tests each entry asks for replace them.
- Built the wheel and inspected its contents.

Sizes are rough: **S** is under half a day, **M** is one to two days, **L** is three days or more.

### Summary of findings

The compliance core is in good shape: the decision rule is centralised, the tests are thorough, and unknowns are reported honestly. The problems fall into four groups.

| # | Finding | Effect | Size |
|---|---|---|---|
| A1 | A rule file can declare `proves: both` for a check that can only prove failure | False **pass** | S |
| A2 | The deep-opening exception is decided on the nominal wall thickness | False **pass** near the threshold | S |
| A3 | A plan with no exterior door passes the entrance obligation | False **pass** | S |
| A4 | Turning space and door maneuvering ignore scale uncertainty | Over-confident verdicts once scale is uncertain | M |
| A5 | The T-shaped turning space is only tested axis-aligned | False **fail** on rotated buildings | M |
| A6 | Rule files are not validated against what each check reads | Crash or silent `unknown` from a typo | M |
| B1–B9 | Crashes, persistence, identifiers, uploads, packaging | Robustness | S–M each |
| C1–C7 | Adoption history, regimes, country handling, typed coverage, engine structure | Blocks M2 local code, M7 and M10 | S–L each |
| D1 | The DXF importer only reads PlanCheck's own exports | **Blocks the rest of M2.5** | L |
| D2 | Nothing draws findings on the plan | Largest visible product gap | M |
| E1 | CI does not run on feature branches | Branch work is untested until merged | S |
| G | New feature: make a draft life safety plan (occupant loads, exit paths, travel distance, common path, dead ends, exit separation and capacity), then check it | Requested feature; method prototyped | L overall |

Do Part A first. A1 to A3 can each produce a `pass` that is not justified, which is the error the specification calls the one that matters.

---

## Part A — Wrong or unjustified verdicts

### A1. A rule file can turn a fail-only check into one that passes

**What happens.** Whether a check can prove a pass is declared only in the rule file (`proves`). The engine trusts it ([engine.py:358](../plancheck/compliance/engine.py#L358)). Nothing ties it to the check function. The specification (§9.4) says the registry enforces that a fail-only check cannot emit `pass`; it does not.

**Observed.** With `proves: both` written into `accessible_route.yaml` and `toilet_room_turning_space.yaml`, a one-room plan returns `pass` for both rules. The rule files load without complaint and `make validate-rules` reports no problem.

**Why it matters.** Local rules for new jurisdictions will be written by hand and reuse these check functions. One wrong line gives a `pass` from a check whose own docstring says it cannot prove one.

**Change.**
1. Give each check a declared capability (see the `CheckSpec` table in A6): `turning_space`, `door_maneuvering_clearance` and `accessible_route_exists` are `fail_only`; `opening_clear_width` and `corridor_min_width` are `both`.
2. In the registry, reject a rule whose `proves` claims more than its check can prove. A `both` check may be declared `both`, `fail_only` or `pass_only`; a `fail_only` check must be declared `fail_only`.
3. In the engine, restrict by the check's capability as well as the rule's: `restrict(restrict(verdict, spec.proves), rule.proves)`.

**Tests.** A rule declaring `proves: both` on each fail-only check raises `RuleError` at load. An engine test that bypasses the registry (a hand-built `ResolvedRules`) still gets `unknown`, not `pass`.

### A2. The deep-opening exception is decided outside the verdict rule

**What happens.** [opening_clear_width.py:64](../plancheck/compliance/checks/opening_clear_width.py#L64) compares the nominal wall thickness with the exception's depth directly. When the thickness is uncertain, the check records an "uncertain deep-opening threshold" note for the governing-requirement logic ([lines 36–43](../plancheck/compliance/checks/opening_clear_width.py#L36-L43)) but still returns a definite verdict against whichever limit the nominal value selects. This breaks the rule that no check compares a value to a threshold on its own.

**Observed.** A door with 850 mm clear width, in a wall of thickness:

| Wall thickness | Verdict | Limit used |
|---|---|---|
| 600 ± 0 mm | pass | 32 in |
| 600 ± 20 mm | **pass** | 32 in |
| 620 ± 20 mm | fail | 36 in |

The middle row is the problem. The wall may be deeper than 24 in (609.6 mm), in which case the 36 in limit applies and 850 mm fails.

**Change.** Decide membership with the verdict functions and combine the two cases:

```python
membership = decide_max(wall.thickness, deep.params["depth"].mm, ctx.k)  # PASS = surely not deep
base = decide_min(measured, rule.requirement["min_clear_width"].mm, ctx.k)
larger = decide_min(measured, deep.params["min_clear_width"].mm, ctx.k)
if membership is Verdict.PASS:
    verdict, required = base, rule.requirement["min_clear_width"]
elif membership is Verdict.FAIL:
    verdict, required = larger, deep.params["min_clear_width"]
else:
    verdict, required = same_or_borderline(base, larger), deep.params["min_clear_width"]
```

Add `same_or_borderline(*verdicts)` to `verdict.py`: the common verdict if all agree, otherwise `borderline`. In the uncertain case the reason states both limits. Keep the existing unresolved-condition note, since it correctly blocks a governing row.

**Tests.** The table above with the middle row expecting `borderline`; the same wall with 950 mm clear passes and with 700 mm fails (both limits agree); σ = 0 results unchanged.

### A3. A plan with no exterior door passes the entrance obligation

**What happens.** `entrance_doors` ([scoping/doors.py:48–55](../plancheck/compliance/scoping/doors.py#L48-L55)) sets `min_count` to 0 when no exterior door exists. The group roll-up then returns `pass` for "at least 0 of 0".

**Observed.** A model whose only door connects a room to itself (no edge to the exterior) gives group `entrances: pass` for both `ada2010.door-clear-width` and `ada2010.door-maneuvering-clearance`, with the reason "at least 60% of entrances (0 of 0) must comply".

**Why it matters.** A model with no exterior door is far more likely an incomplete model than a building without an entrance. Door clear width is a `both` check, so this `pass` survives to the report.

**Change.** Add `unresolved_reason: str | None = None` to `Obligation`. When no exterior door or doorway is modelled, `entrance_doors` returns the obligation with that field set ("no exterior door or doorway is modelled; public entrances cannot be identified"). In the roll-up ([engine.py:403–405](../plancheck/compliance/engine.py#L403-L405)), an obligation with `unresolved_reason` gets `unknown` with that reason, whatever its members. Door-level findings from the room-door obligation are unaffected.

**Tests.** The model above gives `entrances: unknown` for both rules. The three fixtures in `eval/compliance/expected.yaml` are unchanged.

### A4. Two geometry checks ignore scale uncertainty

**What happens.** The corridor check combines wall-face uncertainty with `value × scale_rel_sigma` ([corridor_min_width.py:169–176](../plancheck/compliance/checks/corridor_min_width.py#L169-L176)). Turning space ([turning_space.py:118](../plancheck/compliance/checks/turning_space.py#L118)) and door maneuvering ([door_maneuvering_clearance.py:128](../plancheck/compliance/checks/door_maneuvering_clearance.py#L128)) use wall-face uncertainty only. A second gap: every check treats a missing `scale_rel_sigma` as zero (`model.scale_rel_sigma or 0`), so a model whose scale uncertainty was never established is measured as if exact.

**Observed.** A room 30 mm above the turning-circle minimum, with `scale_rel_sigma = 0.05` (a ±78 mm uncertainty on the diameter): the turning-space measurement still reports σ = 0.5 mm, and both checks return the same verdicts as with exact scale.

**Why it matters.** Harmless today, because both exact input paths set the scale uncertainty to zero. It becomes a source of wrong definite verdicts as soon as M4 and M5 produce models with a real scale uncertainty, and it is exactly what the accuracy budget is meant to study.

**Change.** One helper in `plancheck/compliance/context.py`, used by all three checks:

```python
def length_sigma(
    model: BuildingModel, value_mm: float, faces: int, extra_mm: float = 0.0
) -> float | None:
    """Standard uncertainty of a length measured between `faces` wall faces.

    None when the model's scale uncertainty has not been established.
    """
    if model.scale_rel_sigma is None:
        return None
    return math.hypot(faces * geometry_sigma(model), value_mm * model.scale_rel_sigma, extra_mm)
```

- Corridor: `faces=2` (what it does now). Turning space: `faces=2`, `extra_mm=0.5` for the inscribed-circle tolerance; the T-shape guard band uses the T square size as the value. Door maneuvering: `faces=2` for each depth and latch distance.
- A `None` result makes the check return `unknown` with the reason "scale uncertainty not established".
- Test fixtures that build models by hand must set `scale_source="exact"` and `scale_rel_sigma=0`.
- Regenerate the budget (`make budget`). The turning-space and door-maneuvering rows will change because their σ now counts two faces.

**Decided on November 23, 2026.** `faces × σ` adds face uncertainties linearly, which assumes they are fully correlated and is the conservative choice. Independent faces would give `√faces × σ`, which is less cautious and was not chosen. The choice is recorded in [corridor_width.md](corridor_width.md) and in specification §9.3.

**Tests.** For each check, a near-threshold fixture is decisive with exact scale and `borderline` with 5% scale uncertainty. A model with `scale_rel_sigma=None` returns `unknown` from each geometric check.

### A5. The T-shaped turning space is only tested axis-aligned

**What happens.** `t_fits` ([turning_space.py:75–107](../plancheck/compliance/checks/turning_space.py#L75-L107)) rasterises the room on a grid aligned to the model's x and y axes and tries four orientations. For a room turned relative to the axes, the T is never tried in the room's own direction, so the "sure miss" test ([lines 131–136](../plancheck/compliance/checks/turning_space.py#L131-L136)) reports `fail`.

**Observed.** A T-shaped room (bar 1600 × 950 mm, stem 950 × 650 mm) that holds the T but not the circle:

| Rotation of the whole model | Verdict from the check |
|---|---|
| 0° | pass (reported as `unknown` after the fail-only restriction) |
| 30° | **fail** |
| 45° | **fail** |

The existing rotation tests did not catch this because none of the rotated fixtures contains a bathroom.

**Change.**
1. Find the room's dominant direction: a length-weighted vote of edge directions modulo 90°. Rotate the floor by the negative of that angle about its centroid, run the existing four-orientation search, and rotate the found centre back for the evidence.
2. A T-shape `fail` requires the room to be rectilinear in that frame (every edge within 0.5° of an axis). Otherwise also try each distinct edge direction (longest first, at most eight). If none fits, return `borderline` with the reason "T-shape placement was not searched at every angle in a non-rectilinear room". A raster search over a finite set of angles cannot prove a miss in such a room.
3. Skip the T search when the circle is already a sure pass. It is the slowest step in a run (about 0.18 s per bathroom) and changes nothing in that case.

**Tests.** The table above with all three rows equal. A property-based test (see E5) asserts the verdict is the same for any rotation angle.

### A6. Rule files are not validated against what each check reads

**What happens.** A check reads its parameters by name (`rule.requirement["min_clear_width"]`), and the engine matches filter keys with `getattr(element, key, None)` ([engine.py:81](../plancheck/compliance/engine.py#L81)). The registry validates the general rule shape but not these names.

**Observed.**

| Mistake in a rule file | Result |
|---|---|
| `min_width` instead of `min_clear_width` | Loads; the run dies with `KeyError: 'min_clear_width'` |
| Filter key `room_typ` instead of `room_type` | Loads; every room becomes `unknown: element input missing ['room_typ']` |
| `check: turning_spce` | Loads; `make validate-rules` says all rule files are valid; the run reports "check is not implemented" |

A related gap: the turning-space rule carries `t_arm_clear` and `t_base_clear`, but the check never reads them. A local amendment that changes them would have no effect and nothing would say so.

**Change.** Declare each check's contract next to its function in `plancheck/compliance/checks/__init__.py`, replacing the bare `CHECK_FUNCTIONS` mapping:

```python
@dataclass(frozen=True)
class CheckSpec:
    function: CheckFunction
    element: Literal["opening", "room", "model"]
    proves: Literal["both", "fail_only", "pass_only"]  # the most the geometry can prove (A1)
    requirement: Mapping[
        str, Literal["length", "percent"]
    ]  # every name required; no others allowed
    checked_exceptions: Mapping[str, Mapping[str, Literal["length", "percent"]]]
    needs_connectivity: bool = False
    uses_check: str | None = None  # another check whose rule this one needs
```

| Check | Element | Proves | Requirement names | Checked exceptions |
|---|---|---|---|---|
| `opening_clear_width` | opening | both | `min_clear_width` | `deep-opening` (`depth`, `min_clear_width`), `double-leaf` |
| `door_maneuvering_clearance` | opening | fail_only | `pull_perpendicular`, `pull_beyond_latch`, `push_perpendicular`, `push_beyond_latch` | none |
| `turning_space` | room | fail_only | `circle_diameter`, `t_square`, `t_width`, `t_arm_clear`, `t_base_clear` | `door-swing` |
| `corridor_min_width` | room | both | `min_clear_width` | `short-reduction` (`reduced_width`, `max_length`, `separation_length`, `separation_width`) |
| `accessible_route_exists` | room | fail_only | none | none; `needs_connectivity`; `uses_check="opening_clear_width"` |

Scoping functions get the same treatment (`doors_serving_rooms`: no parameters; `entrance_doors`: `min_share` as a percentage; both need connectivity).

Add `contract_problems(rule) -> list[str]` to the registry and call it from `load_ruleset`, raising `RuleError`. Deletion rules are exempt. It checks:

1. `check` names a known check or scoping function.
2. `selection.element` matches the check's element.
3. Requirement names are exactly the declared set, and each unit is a length or a percentage as declared.
4. Every exception with `handling: checked` is one the check computes, with the declared parameters. Surfaced exceptions may carry any parameters.
5. Every filter key is a field of the element type (`Opening.model_fields` or `Room.model_fields`) or the virtual key `exterior` on openings. For fields with a fixed set of values (`kind`, `operation`), every filter value is one of them.
6. `proves` does not exceed the check's capability (A1).
7. For `turning_space`: `t_width + t_base_clear == t_square` and `t_width + 2 × t_arm_clear == t_square`, within 10⁻⁶ mm. The check places the T that the square and width define; numbers that break the identity describe a different shape, which the check cannot test.

At `resolve` time, also check that every id in `obligated_by` is a scoping rule in the resolved list. Today that surfaces only as a run-time `unknown`.

`make validate-rules` prints these problems. A filter value for `room_type` that is not a value in `configs/room_type_map.yaml` is printed as a warning, not an error.

Remove the hard-coded check names from the engine ([engine.py:238](../plancheck/compliance/engine.py#L238) and [282](../plancheck/compliance/engine.py#L282)) in favour of `needs_connectivity` and `uses_check`.

**Tests.** One test per row of the "Observed" table expecting `RuleError`; one per numbered check above; the seven ADA rule files and the Maharashtra draft still load.

---

## Part B — Crashes and data-handling defects

### B1. One failing check aborts the whole run (S)

The engine calls each check with no error handling ([engine.py:342](../plancheck/compliance/engine.py#L342)). Any exception, such as a GEOS topology error on an odd polygon, loses every other finding.

**Change.** Catch exceptions around the check call. Emit an `unknown` finding with the reason "check could not be evaluated: `<ExceptionType>`", log the traceback, and list the rule and element under a new `errors` entry in coverage. Add `strict: bool = False` to `CheckContext`; when true the exception propagates. The test suite runs strict.

### B2. Malformed tagged drawings raise `KeyError` (S)

`entities_model` indexes metadata directly ([cad.py:120](../plancheck/ingest/cad.py#L120), [134](../plancheck/ingest/cad.py#L134), [140](../plancheck/ingest/cad.py#L140), [144](../plancheck/ingest/cad.py#L144)). **Observed:** a tagged DXF whose opening lacks `wall_id` raises `KeyError: 'wall_id'`. The command-line entry point catches only `ValueError` and `NotImplementedError`, so the user sees a traceback; the web page shows the message `'wall_id'`.

**Change.** Validate each entity's metadata through a small Pydantic model per kind (`WallMeta`, `OpeningMeta`, `RoomMeta`, `FixtureMeta`, `DimensionMeta`, `RouteMeta`), each with `extra="forbid"`. Report missing keys, unknown host walls, and rooms without a boundary as `ValueError` naming the element. Tests: one per missing key and per dangling reference.

### B3. One unreadable project file breaks the project list (M)

`LocalProjects.list()` loads and validates every project in full ([local_projects.py:89–90](../plancheck/local_projects.py#L89-L90)). **Observed:** with one file that fails validation in the folder, `list()` raises and `/api/projects` returns an error, so the page shows no projects at all. Because `Report` and `ProjectSettings` forbid unknown fields, any future change to either makes every previously saved project unreadable. The list also returns every project's complete report, and the page calls it after every save and run.

**Change.**
1. Add `schema_version: int` to `LocalProject`, and a `migrate(raw: dict) -> dict` function applied before validation. Start at version 1; treat a missing version as 1.
2. `list()` returns `ProjectSummary` (id, name, status, revision, whether results exist, last-modified time). A file that cannot be read becomes a summary with `status="unreadable"` and the error text; it never raises.
3. `/api/projects` returns summaries. Add `GET /api/projects/{id}` for the full project, and have the page fetch it when a project is selected.

Tests: a corrupt file alongside a good one lists both; a version-1 file with a since-renamed field loads through `migrate`.

### B4. Every server error is reported as a bad request, and nothing is logged (S)

[web.py:142–143](../plancheck/web.py#L142-L143) turns any exception into HTTP 400 with the raw exception text. A programming error looks like user error, internal paths can leak into the message, and no traceback is recorded. In `do_GET`, exceptions other than `ValueError` and `FileNotFoundError` are not handled at all.

**Change.** Introduce `UserError(ValueError)` for expected conditions in `local_projects.py` and the importers. Return 400 for `UserError` and for Pydantic validation errors (formatted as field and message). Return 500 with `{"error": "Internal error", "reference": "<short id>"}` for everything else, and log the traceback with the same reference through `logging`. Apply the same handling to `do_GET`.

### B5. Different projects export identical IFC GlobalIds (S)

GlobalIds are derived from `project_id` and the element id, and `project_id` defaults to the constant `"plancheck"` everywhere ([ifc.py:364–376](../plancheck/export/ifc.py#L364-L376), [pipeline.py:70–71](../plancheck/pipeline.py#L70-L71)). **Observed:** two different buildings exported through the pipeline share 47 of 47 GlobalIds. Loaded together in a BIM viewer they collide, and a BCF issue from one project resolves to an element in the other.

**Change.** Add a `project_id` parameter to `pipeline.process` and pass it to both `export_ifc` and `export_bcf`. The web flow passes the project's UUID. The command line derives it from the SHA-256 of the source drawing unless `--project-id` is given. Tests: two models give disjoint GlobalIds; the same model and id exported twice give identical ones.

### B6. BCF topic ids depend on list position, and every topic has the same camera (S)

The topic GUID includes the finding's index ([bcf.py:64–67](../plancheck/export/bcf.py#L64-L67)), so any change in the number or order of findings renumbers later topics, and a BIM tool that already imported them sees new issues, not updates. Every viewpoint uses one whole-plan camera ([bcf.py:96–102](../plancheck/export/bcf.py#L96-L102)).

**Change.** Derive the GUID from the project GUID, rule id, sorted element ids and group; append a counter only if two findings share all four. Aim each camera at the bounding box of the finding's evidence, or of its elements when there is no evidence, with a margin. Tests: removing an unrelated finding leaves the other topic GUIDs unchanged.

### B7. Uploads are slow, stored before validation, and never cleaned up (M)

- The browser base64-encodes the file one byte at a time into a string ([app.js:146–148](../web/app.js#L146-L148)) and sends it inside JSON. That adds a third to the size and freezes the tab on large drawings.
- The server writes the file into `uploads/` and only then parses it ([local_projects.py:101–102](../plancheck/local_projects.py#L101-L102)). A file that fails to parse stays there.
- Nothing deletes old uploads or run folders. Each run writes seven output files.

**Change.** Accept the raw file body (`Content-Type: application/octet-stream`, the file name in a header), stream it to a temporary file with the size cap, check the leading bytes (`%PDF-` for PDF; the DXF section header or binary sentinel for DXF), parse it, then rename it into `uploads/`. Delete the temporary file on any failure. Keep the newest three runs per project (a config value) and delete uploads no project refers to when a project is saved. Tests: a failed upload leaves `uploads/` unchanged; a fourth run removes the oldest.

### B8. The server handles one request at a time, and a crash leaves a project stuck (S now, L later)

`LocalServer` is a plain `HTTPServer` ([web.py:35](../plancheck/web.py#L35)), so a check run blocks every other request, including loading the page. `run` saves `status="processing"` before starting ([local_projects.py:173–175](../plancheck/local_projects.py#L173-L175)); if the process dies, the project stays that way.

**Change now.** Use `ThreadingHTTPServer`, a lock per project id around `run`, and at startup mark any `processing` project as `error` with the message "interrupted". **Change later:** background jobs with status endpoints, which is the open M6 task in the checklist and belongs with D3.

### B9. An installed copy of the package cannot run (M)

The wheel contains only `plancheck/` (**observed:** 65 files, none from `rules/`, `configs/` or `web/`). The code finds those folders, and `uv.lock`, relative to the repository root ([config.py:11](../plancheck/config.py#L11), [registry.py:26](../plancheck/compliance/registry.py#L26), [web.py:19–20](../plancheck/web.py#L19-L20), [artifacts.py:24](../plancheck/compliance/artifacts.py#L24) and [216](../plancheck/compliance/artifacts.py#L216)). It works only from a source checkout. A container image for M6 would fail on first use.

**Change.**
1. Add `plancheck/paths.py` with `rules_dir()`, `config_dir()`, `web_dir()` and `data_dir()`. Each resolves in this order: an environment variable (`PLANCHECK_RULES_DIR`, `PLANCHECK_CONFIG_DIR`, `PLANCHECK_WEB_DIR`, `PLANCHECK_DATA_DIR`), then the source checkout, then data packaged inside the wheel. Replace every repository-relative path with these.
2. In `pyproject.toml`, use hatch's `force-include` to copy `rules/`, `configs/` and `web/` into `plancheck/_data/` in the wheel. The top-level folders stay where the specification puts them.
3. Make the lockfile optional in `create_run`: when no `uv.lock` is present, record `dependency_lockfile: null` and rely on the installed-package list the artifact already stores.
4. Add `--host`, `--port` and `--data-dir` to `python -m plancheck.web`.
5. Fix the two paths that depend on the current directory ([demo.py:19](../plancheck/demo.py#L19), [validate.py:90–91](../plancheck/evaluation/validate.py#L90-L91)).

**Test.** A CI job builds the wheel, installs it in a clean environment, and from an empty directory runs `python -m plancheck.compliance.registry` and one check through `plancheck.pipeline`.

---

## Part C — Design changes needed before the next milestones

### C1. Adoption records cannot represent a code change over time (M, before the first real jurisdiction)

An adoption record has an `effective_date` but no end date, and `check_records` rejects two records for one authority ([resolve.py:210–216](../plancheck/jurisdiction/resolve.py#L210-L216)). `local_applicability` only tests that the permit date is not before the effective date ([applicability.py:54–59](../plancheck/compliance/applicability.py#L54-L59)). When a jurisdiction adopts a new edition, the only option is to edit its record in place. The specification forbids that (§3.3), and it silently changes the answer for projects permitted under the old edition.

There are no real records yet, so this is cheap to fix now and expensive later.

**Change.** Move the adoption facts into a list inside the record:

```yaml
name: City of Example
slug: example-city
country: XX
level: place
authority_id: ...
parent: example-state
adoptions:
  - base_code: ...
    base_edition: ...
    effective_date: 2019-07-01
    superseded_date: 2023-01-01     # exclusive; null while in force
    adopting_reference: ...
    source_url: ...
    retrieved_on: ...
    verified_by: ...
  - base_edition: ...
    effective_date: 2023-01-01
    superseded_date: null
    ...
```

- `AdoptionRecord.adoption_for(permit_date) -> Adoption | None`. A validator lifts today's flat fields into a one-entry list so existing test records keep loading.
- Validation rejects overlapping windows and entries out of date order.
- `local_applicability` and `adopted_base_applicability` pick each chain link's adoption by permit date. No adoption in force gives `not_applicable` with the reason "no adoption on record for `<name>` in force on `<date>`".
- Completeness (`missing`) is judged per adoption, so an incomplete old entry does not block a complete current one.
- Rule files already carry their own `effective_date` and `superseded_date`, so one `rules/local/<slug>/` folder can hold rules for successive editions.
- Add the age warning the specification's risk table asks for: a config value `adoption_record_max_age_days`; older `retrieved_on` dates add a coverage note and a flag in the availability panel.

**Tests.** Two successive adoptions with a permit date before the first, inside the first, on the boundary day, and inside the second; overlapping windows rejected; flat records still load.

### C2. Make the regime a property of the ruleset, not of its name (M, before M10 and before any second ADA edition)

The string `"ada_2010"` decides behaviour in four places: whether a base rule needs an adoption chain ([engine.py:149](../plancheck/compliance/engine.py#L149)), which door-width rule a route check uses ([engine.py:283](../plancheck/compliance/engine.py#L283)), the regime label ([governing.py:26](../plancheck/compliance/governing.py#L26)), and amendment protection ([registry.py:27](../plancheck/compliance/registry.py#L27)). The report loops over two fixed regime names ([report.py:88](../plancheck/compliance/report.py#L88)). A 1991 ADA ruleset (specification §3.0, point 4) would be treated as a building code, and M10's guidance regime has nowhere to go.

**Change.** Add a manifest to each ruleset folder, `rules/<ruleset>/_ruleset.yaml`:

```yaml
title: 2010 ADA Standards for Accessible Design
regime: ada              # ada | building_code | guidance
amendable: false         # may another ruleset amend these rules?
requires_adoption: false # must the project's adoption chain include this code and edition?
```

- `load_ruleset` reads it and stores `regime`, `amendable` and `requires_adoption` on `LoadedRule`. A folder without a manifest is an error.
- Add `Regime` as a `StrEnum` in `results.py`; `Finding.regime` uses it.
- Replace the four string comparisons with the manifest fields. The route check picks its door-width rule from the same regime.
- The report iterates over the regimes present, in a fixed order.
- Governing requirements are derived only between `ada` and `building_code`. A `guidance` finding never enters one; assert this in a test now so M10 inherits it.

**Tests.** A second non-amendable ADA ruleset in a temporary rules folder behaves like `ada_2010`. A synthetic `guidance` ruleset produces findings that appear in their own report section and in no governing row.

### C3. Country handling is hard-coded and unvalidated (S)

- [proposal.py:49](../plancheck/jurisdiction/proposal.py#L49) maps only "india", "united states" and "usa" to codes, and otherwise upper-cases the text, so "Canada" is saved as `CANADA`.
- `ProjectSettings.country` and `ProjectContext.country` accept any string, while `AdoptionRecord.country` requires an ISO alpha-2 code. A project saved with `CANADA` can never match a record.
- [index.html:9](../web/index.html#L9) offers only IN and US, lists Maharashtra as the only region, and carries Maharashtra-specific help text.

These break the rule that no country or region is hard-coded in the engine or the page. Removing the page wording is already an M7 task in the checklist; the type fix was added by this review.

**Change.** Add `configs/countries.yaml` with ISO 3166-1 alpha-2 codes and English short names, reviewed by the author. Use the existing `Country` type from `resolve.py` on `ProjectContext.country` and on `ProjectSettings.country` (allowing empty for drafts). Replace the three-entry map with a lookup in that file, matching codes and names case-insensitively; an unrecognised country stays empty with a note, never upper-cased text. Serve the list at `/api/countries` and fill the page's country list from it. Drop the fixed region list; offer regions and authorities only from the adoption-record catalogue for the chosen country.

**Decided on November 22, 2026.** The country table is checked in and holds India and the USA. The alternative, `pycountry`, is LGPL and was not chosen.

### C4. Coverage is an untyped dictionary (S)

`Report.coverage` is `dict[str, Any]` ([engine.py:110](../plancheck/compliance/engine.py#L110)). The report renderer reads it with string keys and `.get` ([report.py:53–117](../plancheck/compliance/report.py#L53-L117)), and the page dumps it as JSON. That breaks the rule that Pydantic types cross module boundaries, and a renamed key fails silently.

**Change.** Define `Coverage` in `results.py` with the fields the engine writes today (`checked`, `not_applicable`, `unknown_applicability`, `not_runnable`, `not_implemented`, `amendments`, `not_visible_on_a_plan`, `notes`, `excluded`, `unresolved`, `surfaced_exceptions`, `governing_not_derived`, `amendment_details`, plus `errors` from B1). `excluded` and `unresolved` hold `Finding` objects, not dumped dictionaries. Bump the run-artifact `schema_version` to 2 and add a loader for version 1, so saved runs still open.

### C5. Split `engine.run` (M, no behaviour change)

`run` is one 357-line function with five nested closures ([engine.py:125–482](../plancheck/compliance/engine.py#L125-L482)). Its steps cannot be tested apart, and it knows individual checks by name.

**Change.** Four functions with typed inputs and outputs, in the same module:

1. `plan_rules(model, resolved, records) -> RunPlan`: applicability for each rule, amendment status, and the rules that cannot run.
2. `run_scoping(model, plan) -> ScopingResult`: obligations and per-scoping-rule status.
3. `run_technical(model, plan, scoping, ctx) -> list[Finding]`: selection, check calls, restriction by `proves`.
4. `roll_up(findings, scoping) -> list[Finding]` and `build_coverage(...) -> Coverage`.

Remove the unused `today` parameter ([engine.py:129](../plancheck/compliance/engine.py#L129), [applicability.py:85](../plancheck/compliance/applicability.py#L85)). Before starting, save the full `signatures()` output for every fixture and generated plan in the test suite as a snapshot; the refactor is done when the snapshot is unchanged.

Do this after A1, A3, A6 and C2, which all touch the same function.

### C6. Checks should return every measurement they make (M, needed for the review queue and the plan overlay)

- Door maneuvering measures up to four distances but returns no `measured` value ([door_maneuvering_clearance.py:166–172](../plancheck/compliance/checks/door_maneuvering_clearance.py#L166-L172)); the report prints "Measurement: not measured".
- The accessible-route check returns a line with no points as evidence ([accessible_route.py:84](../plancheck/compliance/checks/accessible_route.py#L84)), so the route cannot be drawn.
- The review queue (M7) ranks elements by whether their uncertainty can change a verdict. That needs each measurement's margin, which the single `measured` field cannot carry for compound checks.

**Change.** Add to `CheckOutcome` and `Finding`:

```python
class NamedMeasurement(_Base):
    name: str  # e.g. "pull-side depth"
    measured: Measured
    required: str  # as written in the source
    required_mm: float
    relation: Literal["min", "max"]
    verdict: Verdict
```

`measurements: list[NamedMeasurement]`. Keep `measured` as the measurement with the smallest margin, for existing consumers. Door maneuvering returns its four; turning space returns the circle; the corridor returns its minimum and each narrow run. The route's evidence becomes a polyline through the midpoint of each door on the route and a representative point of each room.

Then add `margin_in_sigmas(measurement)` to `verdict.py` and a pure function `review_ranking(report, target_sigma_mm)` that lists findings whose verdict could change if the measurement were confirmed. Both can be built and tested on ground-truth models now.

### C7. Lookups and repeated work (S, low priority)

Measured run time is fine today (32 rooms and 53 openings in 1.5 s, almost all of it the T-shape raster addressed in A5). These will matter for raster-derived models and for re-running checks after each edit in the review queue:

- `BuildingModel.wall()`, `opening()` and `room()` scan lists ([types.py:366–373](../plancheck/model/types.py#L366-L373)); `_check_unique_ids` is quadratic ([types.py:326](../plancheck/model/types.py#L326)). Build id-to-element dictionaries once as private attributes and use a `Counter` for duplicates.
- The route check recomputes every door's width verdict for every room and scans all edges per node ([accessible_route.py:42](../plancheck/compliance/checks/accessible_route.py#L42), [70–74](../plancheck/compliance/checks/accessible_route.py#L70-L74)). Door maneuvering rebuilds the union of all walls for every door ([door_maneuvering_clearance.py:125–127](../plancheck/compliance/checks/door_maneuvering_clearance.py#L125-L127)). Add a per-run cache object to `CheckContext` holding door verdicts, the adjacency map and the obstacle union.

---

## Part D — Product work that unblocks milestones

### D1. A DXF convention a person can draw (L) — blocks the rest of M2.5

**The blocker.** The DXF importer reads only entities on `PC-*` layers that carry JSON in DXF extended data ([ingest/dxf.py:59–82](../plancheck/ingest/dxf.py#L59-L82)). Only PlanCheck's own exporter writes that. The remaining M2.5 tasks ask the author to draw at least twenty plans in CAD and have the importer produce their ground truth, but no CAD program lets a person author that extended data by hand. As it stands, the author-drawn test set cannot be imported, so those tasks cannot start. The tagged vector-PDF path has the same limit.

**Proposed convention** (for the author to approve before any code; the author has to be able to draw to it). It reuses the display layers and the door block the exporter already writes.

| Layer | What the author draws | What it becomes |
|---|---|---|
| `A-WALL` | A polyline along each wall's centerline, with the polyline's constant width set to the wall thickness | One `Wall` per straight segment; thickness from the polyline width, σ = 0 |
| `A-DOOR` | An insert of the block `PC_DOOR_SWING` (hinge at the origin, closed leaf along +x, open leaf along +y), scaled to the leaf width, rotated, and mirrored for handing. Attributes: `ID`, `TAG`, `OPERATION`, and optionally `OPENING_WIDTH_MM` and `CLEAR_WIDTH_MM` | A door on the wall whose axis passes within half a thickness of the hinge. `hinge_at` and `swings_to` come from the rotation and mirroring relative to the wall's direction. `clear_width` is set only if the attribute is present; otherwise the configured deduction applies or the width check returns `unknown`. Nothing is guessed |
| `A-DOOR` | An insert of a second block, `PC_CASED_OPENING` (a unit line), scaled to the opening width | A cased opening |
| `A-GLAZ` | A line along the wall axis, as long as the window | A window |
| `A-AREA-IDEN` | One text inside each room | The room's label, and its `room_type` through `configs/room_type_map.yaml` |
| `A-ANNO-DIMS` | Ordinary dimensions | `Dimension` entries |
| Two new entries in `configs/dxf_layers.yaml` (names for the author to choose) | Closed polylines for fixture footprints; open polylines for corridor paths | `Fixture` and `Room.corridor_paths` |

Units come from `$INSUNITS`, which stays mandatory.

**Rooms and connectivity are derived, not drawn.** Add `plancheck/rooms/build.py`. It is the specification's §8.1 step 7, and the raster path in M4 will reuse it:

1. Node all wall centerlines (`shapely.unary_union`) and polygonize. Each bounded face is a room's gross `boundary`.
2. `clear_polygon` is the boundary minus the union of wall footprints. If the result is not a single polygon, keep the room, add a warning, and let checks that need the clear floor return `unknown`.
3. For each door and cased opening, take two probe points at the opening's centre, offset to each side of the wall by half the thickness plus 50 mm. The room containing each probe is one end of the graph edge; a probe in no room is the exterior. If both probes land in the same room or both in the exterior, add no edge and a warning; the engine already reports missing connectivity as `unknown`.
4. A wall segment with a room on only one side is exterior.
5. Ids are deterministic. Doors use their `ID` attribute. A room's id is its label when that is unique in the drawing, otherwise `R1`, `R2`, … ordered by centroid. Walls are `W1`, `W2`, … ordered by their start and end coordinates. `expected.yaml` refers to these ids, so the ordering is part of the contract.

**Routing.** In `pipeline.py`, a DXF with `PC-*` exact entities takes the existing path; one with `A-WALL` centerline polylines takes the new one; anything else is rejected with a message naming both conventions.

**Deliverables.**
- `plancheck/ingest/dxf_convention.py` and `plancheck/rooms/build.py`.
- `docs/cad-convention.md`, written for the person drawing.
- A script that generates a template DXF containing the layers and both blocks, so drawing starts from a correct file.

**Tests.**
- Build the three review plans with `ezdxf` following the convention (not through the exporter); the imported models reproduce `expected.yaml`. This becomes a third input path in `make eval`.
- Hinge and handing decoding for all four door configurations on walls drawn in each direction, and mirrored.
- Inches, feet and millimetres.
- Rejections: a door not on any wall, overlapping doors, a wall network that encloses no room, missing units, a curved wall segment.
- `rooms/build.py` alone: T-junctions, a room inside a room, an open-plan space, and a property test that derived rooms never overlap.

**Decision for the author.** M2.5's acceptance says the seeded set runs from both DXF and vector PDF. A PDF plotted from ordinary CAD is untagged, and reading it means grouping paths by line weight and detecting arcs, which is extraction work closer to M4. I recommend narrowing the M2.5 PDF requirement to tagged PDFs that PlanCheck exports from the imported DXF, and moving untagged vector PDF to M4. That needs a line in the specification.

### D2. Draw the findings on the plan (M)

Every check already returns evidence geometry, but nothing draws it. The page prints location evidence, coverage and governing requirements as raw JSON ([app.js:53](../web/app.js#L53), [93](../web/app.js#L93), [119](../web/app.js#L119)), and the HTML report is one block of preformatted text ([report.py:150–157](../plancheck/compliance/report.py#L150-L157)). Showing violations on the plan is goal 6 of the specification and the first thing a user will look for.

**Change.**
1. `plancheck/export/svg.py`: `plan_svg(model, report=None) -> str`. It draws wall solids with openings cut, door swings, room outlines and labels, and, when a report is given, each finding's evidence. Each evidence shape carries the finding's id and a class for its verdict. Plan millimetres map to SVG through a single flip transform. Build it with `xml.etree.ElementTree`; never paste drawing text into markup.
2. Rebuild `report.html` as a structured page: the disclaimer and coverage summary first, then the plan drawing, then one table of findings per regime (verdict, element, measured ± uncertainty, required, citation, exceptions), then groups, governing requirements, and the amendment audit. Keep the `.md` output, and make it real Markdown tables. The spec asks for the source unit first with metric alongside.
3. Serve the drawing at `GET /api/projects/{id}/plan.svg` and show it on the page beside the findings table. Selecting a row highlights its evidence, and the reverse. Replace the three JSON dumps with tables.
4. Mark verdicts with text and a symbol as well as colour.

This also depends on C6 for the route polyline and the door-maneuvering measurements.

**Status (November 23, 2026).** Steps 1, 3 and 4 are done, and step 2 is done for the HTML report. The drawing is written to `plan.svg` with every run and the page loads it through the existing download route, so stale results cannot be shown. A finding whose check returns nothing to draw is drawn as the outline of its element. On the plan, `fail` and `borderline` carry the finding's number; an `unknown` or `pass` that has only an element outline is hidden until its row is selected. The HTML report lists problems first and keeps the full text record below the tables. Still open: Markdown tables for the `.md` report, and the route polyline (C6).

**Tests.** The SVG parses; it contains one evidence element per finding that has evidence; a room label of `<script>` appears escaped; rotating the model rotates the drawing consistently.

### D3. Choose the web API framework before M6 (decision, then L)

The server is hand-written on `http.server` with manual routing and JSON handling. The specification lists seventeen endpoints with path parameters, background jobs with status, file uploads, and a database behind them.

**Recommendation.** FastAPI with uvicorn. It gives request and response validation from the existing Pydantic models, an OpenAPI document that the front end can generate types from, streaming uploads, and a test client. Both are believed to be permissively licensed; confirm from installed metadata and log them in `docs/dependencies.md` before adding, as the dependency rule requires.

**Shape.**
- A `ProjectStore` protocol with today's `LocalProjects` as the first implementation, so the PostgreSQL store required by M6 is a second implementation and not a rewrite.
- Jobs start as an in-process worker pool with a job record in the store: `POST …/check` returns a run id at once, and `GET /v1/checks/{run_id}` reports status and, when finished, results. No external queue until one is needed.
- Keep the loopback protections (Host and Origin checks) as middleware.
- B3, B4, B7 and B8 are then solved in the new server; if D3 is approved, do those four there and skip the interim versions.

### D4. Give the front end a structure that can carry M7 (decision, then L)

The page is one HTML file with its CSS on a single line and 195 lines of JavaScript sharing global state. It has no tests and no lint; CI does not even syntax-check it. M7 adds the three-tab bar, the location-first flow, the plan overlay, the review queue, a geometry editor and a 3D viewer.

**Recommendation.** Follow the specification: React with TypeScript, built with Vite, under `web/`. Generate API types from the OpenAPI document (D3), so the page and the server cannot drift apart. Use Vitest for unit tests and Playwright for interaction tests; the open M7 task "complete browser interaction testing" and the keyboard and screen-reader checks for the tabs need a browser test tool in any case. Node is a development-only toolchain; the API serves the built files.

If you prefer no build step, the minimum is: split `app.js` into ES modules, add JSDoc types checked by TypeScript in check-only mode, and add Playwright.

**Fix regardless of that decision (S each).**
- Remove the hard-coded countries, region and Maharashtra wording (see C3).
- Switching projects discards unsaved edits without warning ([app.js:130–139](../web/app.js#L130-L139)).
- `api()` assumes every response is JSON ([app.js:12](../web/app.js#L12)); a non-JSON error shows a parsing error in place of the real one.

### D5. Engine and API groundwork for the location-first flow (S)

The flow itself was already listed under M7 in the checklist. Two prerequisites were not:

- `ProjectContext.jurisdiction_source` still uses the earlier vocabulary (`user`, `address_proposed`, `address_confirmed`). Replace it with `plan_evidence`, `user_location` and `user_named`, plus a separate `jurisdiction_confirmed: bool`. The engine marks building-code findings provisional when the jurisdiction is not confirmed ([engine.py:431](../plancheck/compliance/engine.py#L431) currently tests one enum value). Bump the model `schema_version` and migrate saved runs.
- The web flow never sets `jurisdiction` or `jurisdiction_source` at all ([local_projects.py:183–195](../plancheck/local_projects.py#L183-L195)). Once a verified record exists, the confirmed authority must map to its record's slug here, or local rules can never run from the page.

---

## Part E — Tests and CI

### E1. CI does not run on feature branches (S)

The workflow runs on pushes to `main` and on pull requests ([ci.yml:3–6](../.github/workflows/ci.yml#L3-L6)). Work here is committed and pushed on a feature branch without pull requests, so nothing tests it until it reaches `main`. Change the trigger to every branch push.

### E2. Test the Python version used for development (S)

The matrix covers 3.11 and 3.12. The local environment runs 3.13. Add 3.13.

### E3. Run the project's own gates in CI (S)

Add steps for `make validate-rules`, `make eval` and `node --check web/app.js`. The first two take seconds and are the checks that prove the rule files and the fixtures still agree. After B9, add the wheel install job described there.

### E4. Add a coverage gate (S)

Done on November 23, 2026. `pytest-cov` is in the development group with its licence logged, and `make test` fails under 90% line and branch coverage. The gate is in the Makefile, not in pytest's default options, so running one test file with plain `pytest` does not trip it. Current figures worth raising first: `pipeline.py` 73%, `demo.py` 78%, `registry.py` 81% (its command-line entry point), `web.py` 81%, `providers.py` 0%.

### E5. Property-based metamorphic tests for the checks (M)

The specification (§9.7) asks for these with Hypothesis. Hypothesis is used only in `test_synthetic.py` and `test_verdict.py`; the check-level transform tests use a few fixed angles on plans with no bathroom, which is why A5 went unnoticed.

Add `tests/test_metamorphic.py` with strategies for rotation angle, translation, mirroring and plan variants (including T-shaped and L-shaped bathrooms and a corridor with a pinch point). Properties, each from §9.7:

1. Translating, rotating or mirroring the whole model never changes any finding's verdict.
2. Widening a door never turns a pass into a fail.
3. Adding a fixture or a wall never turns a failed turning space into a pass.
4. Increasing σ never turns `borderline` into `pass` or `fail`.
5. Converting the model to inches and back gives identical verdicts.

Write these first, before fixing A5, and confirm property 1 fails on the current code.

---

## Part F — Documentation and process

### F1. Rule verification status (decision)

All seven ADA rule files have `status: verified` with `verified_by: "Claude Code, 2026-11-05 …"`. The specification says numeric parameters come only from the author, verified against the source, and M2 lists "Author fills and verifies params for the initial ADA rules". The automatic check proves that each quote appears in the stored text and contains its number. It does not prove that the right sentence was chosen, that the exception list is complete, or that the applicability lists and the effective date are right. Governing requirements trust `status == "verified"` ([governing.py:73](../plancheck/compliance/governing.py#L73)).

**Recommendation.** Three states: `draft`, `machine_checked` (quotes match; what the seven files are today) and `author_verified` (requires the author's initials and date). Governing rows and the "verified" label in reports require `author_verified`. Add a short worksheet for the seven rules alongside `eval/compliance/REVIEW.md`. If you have in fact checked them yourself, the simpler fix is to put your name and date in `verified_by`.

### F2. Bring the README and specification in line with the code (S)

- The README still says the tool checks "one jurisdiction's adopted building code", and its quick start does not mention `make web`.
- The specification's §5 listing of `ProjectContext`, `Room` and `BuildingModel` omits fields the code has (`region`, `city`, `planning_authority`, `ada_reference`, `corridor_paths`, `location_extraction`, `schema_version`).
- Done on November 23, 2026: the README says the tool checks the building code adopted by the project's own jurisdiction and has a section for `make web`; the specification's §5 lists those fields; and `PRD.md` was merged into this file, so the README and specification point here.

### F3. The command line applies ADA by default (S)

`pipeline.process` falls back to `["ada_2010"]` when no ruleset is named ([pipeline.py:60](../plancheck/pipeline.py#L60)). The web flow requires an explicit selection, and the rule is that nothing runs by default. Make `--ruleset` required on the command line and remove the fallback; the demo passes it explicitly.

---

## Part G — New feature: making a life safety plan

Requested by the author on November 22, 2026. The scope is India and the USA.

A life safety plan is the sheet in a permit set that shows how people get out of the building: how many people each space holds, where the exits are, how far the longest walk to an exit is, and whether the exits are numerous, wide and far apart enough. This part adds the ability to **make** a draft of that sheet from the building model. **Checking** the same quantities against code limits is a second stage that reuses everything in the first.

The output is a draft egress analysis for the designer to review. It is not a permit-ready sheet, and it keeps the design-assist disclaimer.

### G0. What exists, what is missing, and the stages

| Needed | Today |
|---|---|
| Room areas, gross and net | Present: `Room.boundary` and `Room.clear_polygon` ([types.py:141–184](../plancheck/model/types.py#L141-L184)) |
| What each room is used for | `Room.space_function` exists but nothing reads or sets it ([types.py:154](../plancheck/model/types.py#L154)) |
| Occupancy and sprinkler status | Present on `ProjectContext` and saved from the page ([types.py:254–255](../plancheck/model/types.py#L254-L255)) |
| Which doors are exits | Missing. Exterior doors are known only as graph edges to `EXTERIOR` |
| Walking distance through the plan | Missing. The route check counts doors in the room graph and has no geometry ([accessible_route.py:31–50](../plancheck/compliance/checks/accessible_route.py#L31-L50)) |
| Corridor centrelines | Present where the importer supplies them: `Room.corridor_paths` ([types.py:155](../plancheck/model/types.py#L155)) |
| Stairs, storeys, fire ratings | Missing. `BuildingModel` is one floor ([types.py:292–293](../plancheck/model/types.py#L292-L293)) |
| Rule values that are areas, counts or tables | Missing. A rule parameter is a single length or percentage ([rules.py:15](../plancheck/compliance/rules.py#L15)) |
| A drawing of the plan | Missing (D2) |

The specification already plans `egress_travel_distance` and `occupant_load` as check types (§9.6) and names common path, dead-end length and exit separation as additions. Nothing is implemented.

| Stage | What it delivers | Depends on |
|---|---|---|
| 1. Make | Occupant loads, exit paths, travel distance, common path, dead ends, exit separation and exit capacity for one floor, drawn as a sheet with tables | G1–G7 below; D1 for author-drawn plans; D2 for the drawing |
| 2. Check | The same quantities compared with limits from a verified ruleset, as building-code findings | Stage 1; C1 and C2; an author-verified ruleset for one US and one Indian authority |
| 3. More than one floor | Stairs, storeys, loads arriving from other floors, rated walls shown on the sheet | Stage 1; a model that holds several floors |
| 4. Audit someone else's sheet | Read a submitted life safety sheet and compare its stated numbers with computed ones | Stages 1 and 2; plan parsing (M3–M5) |

Stages 1 and 2 are specified here. Stages 3 and 4 are listed so the design does not block them.

### G1. What the sheet shows

Drawn on the plan:

- **Each room:** its function, area and the area basis used (gross or net), the load factor and the resulting occupant load. A declared load is marked as declared.
- **Each exit:** an identifier, its clear width, its capacity and the occupant load assigned to it.
- **Egress paths:** from the most remote point of each room to its nearest exit, with the length. The longest one on the floor is emphasised and its remote point is marked.
- **Common path of travel:** the first part of a path, up to the point where two separate exits become available, drawn in a different line style with its length.
- **Dead ends:** corridor arms that lead to no exit, marked with their length.
- **Exit separation:** the straight line between exits and the diagonal of the area they serve, each with its length.

In tables beside the plan:

- **Project basis:** occupancy, sprinkler status, the code, edition and authority in use, and whether the ruleset is author-verified.
- **Occupant load schedule:** one row per room, and the total.
- **Egress summary:** for each quantity, the value provided, the value required and the verdict. With no verified ruleset, the required column reads "not checked" and no verdict is shown.
- **Not shown on this sheet:** rated walls and doors, sprinklers, alarms, extinguishers, exit signs, emergency lighting, stairs, areas of refuge, door hardware and furniture. This list is fixed text, so the sheet never implies they were considered.

Line styles and text labels carry the meaning; colour is an addition (as in D2).

### G2. Model and input changes (M)

Bump `BuildingModel.schema_version` to 2 with a migration (the mechanism from B3).

1. **Exit designation.** Add `Opening.exit_role: Literal["exit", "not_an_exit"] | None`. `None` means nobody has said. The analysis proposes every door with a graph edge to `EXTERIOR` as an exit and the user confirms or changes the list. A door into an enclosed stair on an upper floor is marked `exit` by the user; this is what lets Stage 1 handle one upper floor before stairs are modelled. Until the list is confirmed, measurements are drawn and every verdict that depends on exits is `unknown` with the reason "exits not confirmed".
2. **Room function.** Start using `Room.space_function`. Add `configs/space_functions.yaml`: PlanCheck's own list of function ids with display names. The importer proposes a function from the room label through `configs/room_type_map.yaml`, and the user confirms it. A room with no function has an `unknown` occupant load; it is never given a default.
3. **Declared occupant load.** Add `Room.declared_occupants: int | None` for rooms where the designer sets the number (fixed seating, a posted limit). A declared value replaces the calculated one and is labelled.
4. **Obstacles.** Fixture footprints are removed from the walkable area. Furniture is not in the model, which is why two distances are reported (G3).
5. **Project facts for Stage 2.** Add fields such as the number of storeys or building height only when a verified rule needs one, each as `None` until entered.

**Tests.** A version 1 model loads as version 2 with no exits designated; a model with no exterior door reports "no exit" and does not fail silently (the same defect class as A3).

### G3. Walking distance on the plan (L)

Add a package `plancheck/egress/`. It measures; it never decides.

**Method.** The shortest path between two points in a floor plan is a chain of straight segments that bends only at wall corners. So the calculation is exact geometry, with no grid:

1. **Walkable space.** Union every room's `clear_polygon` with the gap rectangle of each door and cased opening (`opening_gap`, [geometry.py:39–43](../plancheck/model/geometry.py#L39-L43)), then subtract fixture footprints. Windows are not passable.
2. **Nodes.** One node per exit, at the centre of its opening, and one node per corner of the walkable space that points into it (a reflex vertex).
3. **Visibility graph.** Join two nodes when the straight segment between them stays inside the walkable space. Use shapely's vectorised `covers` on a prepared polygon.
4. **Distance to an exit from every node.** Dijkstra from all exits at once, keeping each node's predecessor and nearest exit.
5. **Distance from any point `p`.** The smallest value of `distance(node) + |p − node|` over the nodes visible from `p`. Sort the nodes by that sum and test visibility in order; the first visible one is the answer.
6. **Most remote point.** Search each room by subdividing squares. A square lying wholly inside the room cannot contain a point farther than its centre's distance plus half its diagonal, so squares that cannot beat the current best are discarded and the rest are split. Room corners are always candidates. Stop at a tolerance of 1 mm, and report the tolerance as part of the measurement's uncertainty.
7. **The path.** Follow predecessors from the remote point to the exit. This polyline is the evidence geometry.

**Two distances, as the specification requires.** The exact shortest path is the least anyone could walk, so it is a lower bound. The second figure is the same path measured at right angles, as the sum of `|Δx| + |Δy|` of each segment in the building's dominant direction (the frame from A5); a reviewer who does not know the furniture layout commonly measures this way. For a maximum limit: at or under the limit on the right-angle figure is `pass`, over the limit on the shortest figure is `fail`, and between the two is `borderline`. Both go through `decide_max`; no check compares numbers itself.

**Clearance from walls.** Reviewers measure the path a set distance clear of walls and corners. That distance is a code value, so it is a rule parameter, null until verified. When set, the walkable space is inset by it before step 2, limited at each door so the door stays passable. When null, the path touches corners, the result is labelled as a lower bound, and it can support `fail` but not `pass`.

**Uncertainty.** Combine the search tolerance, the wall-position uncertainty for the faces the path touches, and scale uncertainty on the whole length, through the `length_sigma` helper from A4. A model whose scale uncertainty is not set gives `unknown`.

**Prototype result.** I built steps 1 to 5 with uniform sampling in place of step 6 and ran it on four shapes with hand-computed answers, each at 0°, 30° and 45°. These become the first known-answer tests.

| Shape | Exact answer | Prototype error |
|---|---|---|
| 10 m × 6 m room, exit at the middle of a long wall | 7,810.25 mm | −1.4 mm |
| L-shaped room, path bends at the inside corner | 13,293.87 mm | −1.4 mm |
| 2 m corridor ring around a 6 m core, one exit | 13,211.10 mm | −20 to −69 mm |
| 30 m × 2 m corridor, an exit at each end | 15,033.30 mm | −14 to −53 mm |

- Where the remote point is a corner, the result is exact; the 1.4 mm is the inset used to keep corner samples inside the room.
- Where the remote point is a tie between two routes, uniform sampling at 100 mm undershoots by up to 71 mm, which is the bound the method predicts. Step 6 exists to remove that undershoot, because undershooting a maximum is the unsafe direction.
- Rotation changed no result beyond that bound, so this method does not repeat defect A5.
- On generated plans it took 0.1 s for 3 rooms, 0.5 s for 5 rooms on a 40 m × 20 m floor, and 8.6 s for 17 rooms on an 80 m × 40 m floor with 50,000 sample points. Step 6 evaluates far fewer points; set a budget of 2 s for a 30-room floor and test it.

It needs no new dependency. The specification suggests a raster distance transform with scikit-image; the exact method avoids both the dependency and the grid error, so update §9.6 to match.

**Tests.** The four shapes above, within 1 mm. Property tests: translating, rotating or mirroring the model does not change the distance; adding an exit never increases it; adding a wall never decreases it; widening a door never increases it; scaling the model scales it.

### G4. Occupant load (M)

`occupants = area ÷ area per person`, by room, where the load factor and whether it applies to gross or net area both come from the ruleset's table for the room's function.

- **Area and its uncertainty.** Gross area from `boundary`, net from `clear_polygon`. The uncertainty is the perimeter times the wall-position uncertainty, combined with twice the relative scale uncertainty times the area.
- **Rounding.** Whether a fraction rounds up is a code convention, so it is a rule parameter.
- **Near a threshold.** The count carries a low and a high value from the area uncertainty. A later check that compares the count with a threshold (for example, the load above which a room needs two exits) returns `borderline` when the threshold falls between them.
- **No factor.** A function the ruleset's table does not list gives `unknown` for that room, and the floor total becomes "at least" the known sum.
- **No ruleset.** The sheet shows areas and declared loads only. The page lets the user enter a load per room so a sheet can still be made.

This is a derived quantity, not a verdict, as the specification says. Other checks consume it.

**Tests.** Gross and net fixtures chosen so the wrong basis gives a different count; rounding at an exact multiple; a room 1 mm either side of a count boundary with and without uncertainty.

### G5. The egress network: common path, dead ends and door loads (L)

Travel distance needs only G3. The next three quantities need to know where routes separate, and a walking path in an open room can always be shifted sideways, so "separate" must be defined on bottlenecks. Build one network per floor:

- a node for each room that is not a corridor;
- for each corridor, the graph of its centrelines from `corridor_paths`, with a node at every junction and end;
- an edge for each door, attached to a corridor at the nearest point of its centreline;
- a node for each exit.

A point in the network has **two ways out** when two routes from it reach two different exits without sharing a door or a centreline segment (`networkx` edge-disjoint paths).

1. **Common path of travel.** For a room, follow the route from its most remote point to the nearest exit. The common path ends where the route first reaches a network point with two ways out. Its length is the G3 distance from the remote point to that place. If the room itself has two ways out, the length is zero. If the floor has one exit, it equals the travel distance. The result is the earliest place the routes could separate, so it is a lower bound: the rule that uses it declares `proves: fail_only` until the author has compared it with hand-measured examples.
2. **Dead ends.** A dead end is a corridor branch whose far end reaches no exit and no room with two ways out. Its length runs along the centreline from the junction where two ways out exist to the end of the branch. A corridor with no centrelines gives `unknown`, as the corridor-width check already does.
3. **Door and exit loads.** Assign each room's occupants to exits and sum the load through each door on the way. Two assignment methods are in use among designers: all to the nearest exit, or split equally among the exits the room can reach. Which one the sheet uses is a decision for the author; the method is printed on the sheet.

**Tests.** A room off a corridor with an exit at each end (common path ends at the room door); the same corridor with both exits at one end (common path runs to the junction); a single-exit floor; a corridor with a stub past the last door; a ring corridor (no dead end).

### G6. Exit count, separation and capacity (M)

These use G3 to G5 and add little geometry.

1. **Number of exits.** Provided: the confirmed exits a room or the floor can reach by separate routes. Required: from the ruleset's table by occupant load. Combined with the existing three-valued helpers.
2. **Exit separation.** The diagonal is the largest distance between two points of the area served, taken from its convex hull. The separation is the distance between two exits. Where on each door to measure from, whether the distance may follow a corridor, and the required fraction of the diagonal (which depends on sprinkler status) are rule parameters.
3. **Capacity.** A door's capacity is its clear width, from the existing `CheckContext.clear_width` ([context.py:42–62](../plancheck/compliance/context.py#L42-L62)), divided by the width required per occupant. Compared with the load assigned in G5. A door whose clear width is unknown has unknown capacity.
4. **Door swing direction (optional).** Whether a door on an egress path swings in the direction of travel is computable from `swings_to` and the path, for rooms above a load the ruleset names.

**Tests.** Boundary fixtures generated from the rule values at one unit below, at, and one unit above each threshold, as §9.7 requires; a missing sprinkler status gives `unknown`.

### G7. Rule format changes (M)

1. **Units.** Extend `Unit` ([rules.py:15](../plancheck/compliance/rules.py#L15)) with areas (`ft2`, `m2`), area per person, width per person, and a count. Each gets an exact conversion, as lengths have.
2. **Tables.** Add `tables` to `Rule`: named lists of rows, each row holding the conditions it applies under (for example `space_function`, or `occupancy` with `sprinklered`) and its parameters. A lookup that matches no row returns `unknown` and names the missing condition. A verified rule cannot contain a null cell, as today.
3. **Function mapping.** Each ruleset's load-factor table maps PlanCheck function ids to that code's rows. The mapping is part of what the author verifies.
4. **Contract.** Each new check declares its element, what it proves, its parameters and its tables in its `CheckSpec` (A6), so a rule file that names a missing table is rejected at load.
5. **Rules without stored text.** The codes involved here are copyrighted, so `source_text` stays null and the quote check does not run. Such a rule can only be `draft` or `author_verified` under F1; there is nothing for a machine to match it against.

### G8. Running it, and what it returns (M)

- `plancheck.egress.analyse(model, load_factors=None) -> EgressAnalysis`: frozen Pydantic types holding the occupant loads, the exits, the distance results with their path polylines, common paths, dead ends, separations and door loads. It needs no ruleset and no jurisdiction.
- **Stage 2 checks** (`egress_travel_distance`, `common_path`, `dead_end_length`, `exit_count`, `exit_separation`, `egress_capacity`) are ordinary check functions registered in `CHECK_FUNCTIONS`. They read the analysis from a per-run cache on `CheckContext` (C7), so the network is built once per run.
- **Regime.** Egress rules belong to the adopted building code. They run only under a confirmed adoption chain and are provisional otherwise, like every local rule. They never mix with ADA findings.
- `plancheck.egress.sheet(model, analysis, report=None) -> LifeSafetySheet`: joins the analysis with the egress findings from a report when there is one. This is the single input to every output format.
- **Saved runs.** Store the analysis and the inputs it used in the run artifact (schema version bump), so a sheet can be regenerated from a saved run.
- **Coverage.** Add the egress quantities that could not be computed, and why, to the typed coverage (C4).

### G9. Drawing the sheet (M, after D2)

- **SVG first.** Extend `plancheck/export/svg.py` from D2 with an egress layer and the tables in G1, composed into one sheet with a title block, north-up plan, legend and the disclaimer. Drawing text is escaped, as D2 requires.
- **DXF.** Write the same content onto its own layers, named in `configs/dxf_layers.yaml`, so a designer can place it in their own sheet set. Paths are polylines and loads are text; tables are text in a block.
- **HTML report.** Add the sheet and its tables as a section of `report.html`.
- **PDF later.** The browser can print the SVG sheet to PDF. A native PDF needs a drawing library, which is the same pending decision as the M7 task "native PDF assessment-report downloads".

**Tests.** The SVG parses; every room with a load has one tag; every path in the analysis appears once; the summary table's numbers equal the analysis values; no verdict text appears when no ruleset was used.

### G10. Page and API (M)

Put this inside the **Building code** tab as its own view with its own run and downloads, because Stage 2 uses the same jurisdiction and inputs. Whether it should be a fourth tab instead is a decision for the author.

1. **Confirm exits:** the exterior doors are listed and highlighted on the plan, pre-selected; the user adds or removes.
2. **Confirm room functions:** a table of rooms with the proposed function and an optional declared load.
3. **Run:** `POST /api/projects/{id}/life-safety` stores the result with the revision; `GET /api/projects/{id}/life-safety.svg` and `.dxf` serve the outputs. Changing the drawing or these inputs marks the result out of date, as for check runs.
4. **Review:** the sheet beside the tables; selecting a row highlights its path.

### G11. Evaluation

- Add egress cases to the author-drawn CAD test set (D1): at least one single-exit floor, one two-exit floor with a corridor, one with a dead end, and one with a room large enough to need two exits.
- The author measures travel distance, common path and dead-end length by hand on each and records them in `eval/egress/expected.yaml` with a tolerance. `make eval` compares.
- Add the egress quantities to the accuracy budget (`make budget`), so later extraction work knows how much wall-position error a travel distance tolerates.

### G12. Limits to state plainly

- One floor at a time. Loads arriving from other floors, stair capacity and exit discharge are Stage 3.
- No furniture or partitions below wall height, hence the two distances.
- The tool does not design: it does not place exits, rate walls or choose protection systems.
- Stage 2 produces nothing until an author-verified ruleset exists for the project's confirmed authority.

---

## Order of work

Until the demo is recorded, the demo-first route near the top of this file sets the order. The numbered order below the demo line comes next. The phases below are the order for the remaining deferred work.

Each phase ends with `make lint`, `make test`, `make validate-rules` and `make eval` passing, and with the checklist in this file updated. Phases 1 and 2 are M2 work, phase 3 is M2.5, and phases 4 and 5 prepare M6 and M7, so the one-milestone-at-a-time rule holds.

| Phase | Items | Why in this order |
|---|---|---|
| 0. Safety net | E1, E2, E3, E5 | CI on the branch, and the property tests that should fail before the fixes |
| 1. Verdict correctness | A1, A2, A3, A6, then A4, A5, B1 | A6's `CheckSpec` is the base for A1; A4 and A5 change measured values, so regenerate the budget once, after both |
| 2. Rules and jurisdictions | C1, C2, C3, C4, C5, C7, F1, F3 | Must be in place before the first real adoption record and local ruleset are written |
| 3. Unblock M2.5 | D1, B2, B5, B6 | The author can then draw the test set; exports from it get correct identifiers |
| 4. Service foundations | B9, D3, then B3, B4, B7, B8 in the new server | Packaging first, so the service can be containerised |
| 5. Product surface | C6, D2, D5, D4 | The plan overlay is the first M7 deliverable that changes what a user sees |
| 6. Life safety plan, Stage 1 | G2, G3, G4, then G5, G6, G7, G8, then G9, G10, G11 | Needs A4, A6, C4 and C7 from earlier phases, D1 for drawn plans and D2 for the sheet. G3 can start as soon as phase 1 is done, because it depends only on the model |
| 7. Life safety plan, Stage 2 | The six egress checks and one verified ruleset each for a US and an Indian authority | Needs C1, C2 and the author's verified values |

Phases 0 and 1 are roughly a week of work by the sizes above. Phase 3 depends on the author approving the drawing convention; phase 4 depends on the framework decisions.

## Checked and found sound

These were examined and need no change:

- The single decision rule holds everywhere except A2. Checks return measurements, and `verdict.py` decides.
- The fail-only restriction is applied in one place in the engine. The gap is in what the rule file may declare (A1), not in the mechanism.
- Quote verification against the stored ADA text works as documented.
- The HTML report escapes drawing text and links only `http` and `https` citations.
- Downloads are limited to a fixed list of file names under UUID-named folders, so a request cannot reach other files.
- The Host and Origin checks block requests from other sites and DNS-rebinding against the local server.
- Capturing engine provenance for each run costs about 0.07 s; it does not need caching.
- Applicability never substitutes today's date for a missing permit date.
- Saved runs store the rules, adoption records and verdict settings they used, and replay from them without reading current rule or config files.
