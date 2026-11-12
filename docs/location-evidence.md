# Location evidence from site-plan text

This backend sub-step extracts **unconfirmed hints**, not a resolved legal
jurisdiction. It works independently of the exact-geometry importer: ordinary
vector-text PDF files need no PlanCheck tags or drawing scale.

```sh
uv run python -m plancheck.jurisdiction.extract site-plan.pdf \
  --output out/location-evidence.json
uv run python -m plancheck.jurisdiction.extract site-plan.dxf \
  --output out/location-evidence.json
```

The JSON includes candidate address, country, state/region, city/municipality,
named planning authority, and jurisdiction-hint fields. Each candidate retains
its source text, source-file hash, source page or DXF layout, and text-fragment
anchor. DXF attribute evidence also retains the original attribute tag and entity
handle. Repeated values are grouped while keeping every evidence occurrence;
conflicting values are retained and the result is marked `ambiguous`.

Every result requires confirmation. No project jurisdiction, permit date, adoption
record, ruleset, or verdict is changed by extraction. The module does not call a
geocoder or external service. A field named jurisdiction is retained as a hint;
it does not establish that the named city is the responsible authority.

## Supported input

- PDF: extractable text across multiple pages, using explicit English field labels.
  Encrypted documents must be decrypted first. Pages without extractable text are
  listed for OCR/manual review; their absence does not prove the page is blank.
- DXF: model/paper-space TEXT and MTEXT, plus INSERT attribute values with recognized
  tags such as SITE_ADDRESS, CITY, or PLANNING_AUTHORITY. Fixed/nested block text is
  not expanded by this first implementation.
- Explicit labels include Site Address, Project Address, Site Location, Address of
  Site, Country, State/Region, City, Municipality, Planning Authority, Special Planning
  Authority, Local Authority, and Local Jurisdiction. Colon and equals separators
  are accepted. Labels begin a logical text line; inline multi-column associations
  are not inferred. Unicode values are preserved; translated/non-English label detection
  is future work.
- Multiline addresses can continue inside the same extracted text fragment.
  Separate label/value fragments are not spatially guessed: empty recognized labels
  are listed as unresolved. Generic office/architect addresses and unlabelled place
  names are not promoted to site addresses.

## Coordinate provenance

PDF anchors are in native, unrotated PDF user space. Crop box, page rotation and
UserUnit are retained for a future viewer to apply the display transform. They
are fragment anchors supplied by the text parser, not exact word bounding boxes;
multiline word offsets have not been reconstructed. DXF anchors are converted to
millimetres only when units are declared, otherwise they remain explicitly in
native drawing units.

## Integration and next work

Supported geometry importers attach the structured result to
`BuildingModel.location_extraction`; saved run artifacts preserve it. The pipeline
also writes `location-evidence.json`, and readable reports show the hints as
UNCONFIRMED with their provenance. The older address warning remains available
for callers already displaying it.

The local webpage matches named-authority hints to supported records and presents
evidence for confirmation/correction. A geographic proposal may require an explicit geocoder action under the
existing supported-country restrictions. OCR and automatic Maharashtra authority
resolution remain unimplemented. Users can always enter/correct location details
manually when extraction is missing, ambiguous, or unsupported.

## Local confirmation webpage

Run `make web`, then open `http://127.0.0.1:8000`. Upload a vector-text PDF or
DXF, inspect each hint and its provenance, and explicitly apply hints as draft
fields. Existing settings are not overwritten by uploading. Conflicting fields
are omitted from the proposal; missing or unsupported evidence requires manual
entry. Country and an exact named planning-authority match are required to propose
an active adoption record. City and generic jurisdiction hints never establish
an authority. Matching is offline and makes no Census requests.

The form includes country, region (including India → Maharashtra), municipality,
responsible authority, permit date and an explicit ADA reference preference.
Save an incomplete draft or confirm completed settings. Projects and evidence
persist locally in `out/projects/`; reopen them using the project dropdown.
Changing settings increments the revision, clears stored check results and marks
the project as requiring a new run. This is a local single-user setup flow,
not the M6 production API/database or the full M7 editor.

Availability lists recorded editions, effective dates and source links when
records exist, checks parent completeness and permit-date applicability, and
always labels local code **not checked**. The page can run an explicitly selected
ADA reference comparison, but it does not execute local-code checks.
There are currently no active verified adoption records in this checkout. The
Maharashtra scaffold is intentionally excluded; save manual authority details
without activating unverified rules. OCR remains pending; image-only PDF pages
are identified for manual review. Uploaded source bytes, extracted evidence and
the source hash persist locally with the saved project.

## Exact-input reference runs

1. Generate sample inputs with `make demo`, or supply a drawing conforming to the
   [exact-input convention](exact-input-demo.md).
2. Upload the drawing, review/correct location, supply the permit date, and select
   **Include ADA as an explicit reference comparison**. Optional project inputs
   and a PDF scale override are available under **Check inputs and PDF scale**.
   Leave unknown facts blank; they remain unresolved in findings.
3. Confirm and save the project, then choose **Run ADA reference checks**.
4. Review findings, citations, measurement uncertainties, coverage and comparison
   limits. Download HTML/Markdown reports, the reproducible run JSON, DXF, IFC,
   GLB or BCF. Native PDF assessment reports remain pending.

Runs are synchronous on this local single-user server. The page shows processing
while the request runs. Each run captures the saved project revision, drawing
hash, settings and existing engine/rule provenance. Ordinary untagged drawings may
provide location text but cannot supply exact geometry: they fail explicitly and
produce no verdicts. Image-only PDFs still require the pending raster/OCR path.

Reopening a project restores its saved drawing, settings and current results.
Changes to a drawing, check inputs, scale or location invalidate the results and
block old download URLs until a new run succeeds. A failed run exposes its error
and removes partial outputs. The server does not infer legal ADA applicability,
activate Maharashtra scaffolds, or call a geocoder. Source uploads are stored in
`out/projects/uploads/`, and runs in `out/projects/<project-id>/runs/<run-id>/`;
these generated files remain excluded from Git. Existing location-only drafts
can be reopened; upload and save a source drawing before their first run.
