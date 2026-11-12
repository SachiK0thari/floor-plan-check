# Exact-input engineering demo

Run `make demo`, then open `out/demo/wide/dxf/report.html`. Each of the `wide`,
`narrow`, and `missing` folders contains a CAD drawing, tagged vector-PDF plot,
project-context JSON, and results from both input paths. Every output folder has a
saved run, readable HTML/text report, IFC, BCF issue archive, DXF, and GLB.

```sh
make demo
make eval
make budget
uv run python -m plancheck.pipeline out/demo/wide/source.dxf \
  --project out/demo/wide/project.json --output out/check
uv run python -m plancheck.pipeline out/demo/wide/source.pdf \
  --project out/demo/wide/project.json --output out/pdf-check
```

Use `--ruleset` repeatedly to select explicit rulesets. Rule/adoption verification
still gates local execution. Omitted project inputs remain unknown. Candidate site
addresses from drawing text are review notes; no geocoder is called automatically.

## Supported DXF contract

The normal DXF exporter retains its AIA display layers and `PC_DOOR_SWING` blocks
with their existing size/operation attributes. It also writes an exact semantic
layer set, marked non-plotting. Those entities are the import contract:

| Layer | Geometry | Required semantic data |
|---|---|---|
| PC-WALL | One straight axis segment | ID, measured thickness, exterior flag |
| PC-OPENING | Locator point on host wall axis | ID, wall ID, kind, gap/leaf/clear widths, operation, hinge/swing, optional two connected room IDs |
| PC-ROOM | Closed net floor polygon | ID, room type, label |
| PC-BOUNDARY | Closed gross room polygon | Matching room ID |
| PC-ROUTE | Open polyline | Room ID |
| PC-FIXTURE | Closed footprint | ID, kind, room ID |
| PC-DIMENSION | Two-point line/polyline | ID, text, measured value |

Semantic properties are JSON mappings split across DXF XDATA strings under the
`PLANCHECK_EXACT_V1` app ID. They contain element properties, not a hidden complete
building model or alternative vector coordinates. All dimensional property names
ending in `_mm` remain explicitly in millimetres. Entity coordinates use the
mandatory `$INSUNITS` header; import converts them to millimetres. Opening position
is projected from the actual locator vector, not copied from a serialized model.
A-AREA-IDEN text is read by room containment when unambiguous. IDs and graph links
are explicit; missing links remain unresolved rather than inferred.

Missing units/data, curved polylines, missing boundaries, invalid IDs, and locator
points off their host wall are rejected. Arbitrary third-party CAD files without
this convention are not yet supported. Editing display outlines alone does not
change semantic axes; keep the exact layer geometry/properties consistent.

## Supported vector-PDF contract

`export_vector_pdf` plots those actual vector coordinates at a declared drawing
scale. Marked-content dictionaries (`/PC`, `/Kind`, `/Metadata`) identify each
entity's properties; the `m`/`l`/`h` operators supply its geometry. The PDF metadata
declares millimetres per PDF point and the plot-origin translation. Import applies
graphics transformations and explicit scale; a manual scale must agree with a
stored scale. Room labels are read from positioned text when unambiguous. Source
text is data, not instructions.

The first implementation supports single unencrypted pages, straight tagged
paths, default page rotation/UserUnit, and explicit plot scale. Form XObjects,
curves, untagged ordinary CAD plots, OCR, and raster extraction are not implemented.
The plot uses a built-in ASCII font; non-ASCII labels are visually escaped while
their original Unicode semantic metadata is retained. Independent multilingual
PDF/text validation remains required. Raster/image-only PDFs are routed to an
explicit unimplemented raster path and never produce guessed verdicts.

PDF parsing uses pypdf (BSD-3-Clause), checked against installed metadata and the
[upstream licence](https://github.com/py-pdf/pypdf/blob/main/LICENSE).

## Reports and BCF

Reports are rendered from the saved run artifact. Coverage/disclaimer appear
before findings. Each source/group finding includes element IDs, measurements,
standard uncertainty, requirements, verdicts, reasons, citations, obligations, and
surfaced exceptions. HTML escapes drawing text and links only HTTP(S) citations.
HTML is self-contained and printable; native PDF assessment reports are not yet
implemented. The source drawing PDF is distinct from an assessment report.

BCF 2.1 exports fail, borderline, and unknown findings, including groups. Topics
contain descriptions, citations and orthographic top-down viewpoints. Component
IDs are derived using the IFC exporter's stable GUID convention, then checked
against the actual supplied IFC file before writing. A mismatched project or
missing element rejects the archive. Project-wide unknown findings have no
invented component reference. Snapshots are optional and currently omitted.

The XML follows the published buildingSMART schemas:
[markup](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_2_1/Schemas/markup.xsd),
[viewpoints](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_2_1/Schemas/visinfo.xsd),
[version](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_2_1/Schemas/version.xsd).
The generated [schema/GUID validation record](../eval/reports/bcf-schema-validation.json)
records local checks against those XSDs and the corresponding IFC files.
IFC/BCF viewer interoperability and the external buildingSMART IFC validation
remain author acceptance checks, distinct from automated GUID/XML tests.

## Validation and remaining acceptance work

`eval/compliance/expected.yaml` contains analytic per-element/per-rule and group
expectations for three synthetic review fixtures, including unknown and excluded
results. They were prepared from simple dimensions and checked by automated tests;
they have **not** been independently hand-checked by the author. The manifest says
`pending_author_review`. `python -m plancheck.evaluation.validate --require-reviewed`
refuses to accept them until signed off. Do not change review status merely to
bypass that gate. Translations, rotations, reflection/handedness, corridor
monotonicity, uncertainty boundaries, and DXF unit round trips have automated tests.

The demo verifies both exact paths against these same expectations. This is an
engineering/synthetic round trip, not the independent author-drawn CAD evaluation
set required by the specification. Author-drawn seeded violations, registration
fiducials, independent CAD PDF plots, found plans, blind annotations, and real
local-code cases remain outstanding. No headline extraction/compliance accuracy
claim follows from these fixtures.

`make budget` generates a seeded preliminary sensitivity table and full JSON at
`eval/reports/accuracy-budget.*`. It perturbs coherent floor-width and clear-width
parameters, wall endpoints, and isotropic scale; invalid models count as changed.
Results cover the implemented check types at the documented boundary margins.
Each setting records verdict counts and Wilson intervals. Budgets use a contiguous
sampled range whose lower confidence bound reaches the configured retention
criterion. DPI conversion assumes uniform pixel quantization at the stated plot
scale; it excludes OCR, localization bias and missed objects. These conditional
synthetic budgets are not validated production upload thresholds. Geometry and
scale have not been perturbed jointly, and local-code budgets await verified rules.

For the first real local jurisdiction, see
[Maharashtra verification](maharashtra-verification.md). The authority, permit-date
range, adopted editions, amendments, source permissions and numeric parameters
still require author-verified input.
