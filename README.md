# PlanCheck

PlanCheck turns a floor plan into a structured, editable building model (walls, doors, windows, rooms), exports it to DXF, IFC, and glTF, and checks it against the 2010 ADA Standards and one jurisdiction's adopted building code. Each finding is drawn on the plan with the measured value, the required value, and the cited section.

> **This is a design-assist tool, not a code review.** It checks a small number of provisions, and it cannot see anything that is not drawn on a floor plan. A report with no findings does not mean a design complies. The code that applies depends on the jurisdiction, the edition it adopted, and the project's permit date. Verify every result against the adopted code.

## Status

Early development. The project is built in milestones; progress is tracked in [PRD.md](PRD.md), and the full specification is in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md). Results tables will be added here from the generated evaluation report.

## Setup

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```
make setup
make lint
make test
```

## Exact-input engineering demo

```sh
make demo
make eval
make budget
```

Open `out/demo/wide/dxf/report.html`. The generated folders include saved runs,
readable reports, IFC, BCF, DXF and GLB from both exact input paths. This uses three
synthetic fixtures pending independent author review. The importer supports an
explicit semantic DXF/tagged-PDF convention; ordinary untagged drawings and raster
extraction remain future work. See [supported inputs and acceptance gaps](docs/exact-input-demo.md).

Ordinary PDF/DXF location text can now be extracted independently of geometry import,
with unconfirmed candidates and source-page/position evidence. See
[location evidence extraction](docs/location-evidence.md) for the command and supported labels.

## How it decides

Every pass or fail comes from a deterministic geometry check on the building model. Each measurement carries an uncertainty, and a result is only called a pass or a fail when the measurement clears the requirement by more than that uncertainty. A language model explains results and cites code text; it never decides them.

## Licences and data

- The segmentation model is trained on CubiCasa5K, which is licensed CC BY-NC 4.0. The trained weights are released for non-commercial use only.
- The International Building Code is copyrighted. This repository stores section numbers, short paraphrases, and numeric requirements, and links to the publisher for the text.
- Dependency licences are listed in [docs/dependencies.md](docs/dependencies.md).

Run `make web` and open http://127.0.0.1:8000 for local drawing-location review, manual authority selection, confirmation and saved project drafts. Supported semantic DXF/tagged PDF drawings can run an explicitly selected ADA reference comparison and download findings, reports and model exports. OCR and local-code execution remain pending. See [location evidence](docs/location-evidence.md#local-confirmation-webpage).
