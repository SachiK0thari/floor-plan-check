# Dependencies and licences

Licences are read from each package's installed metadata (`importlib.metadata`), not from memory.
The spec's rule (§16): ask the author before adding a copyleft dependency.

## Runtime

| Package | Licence | Used for | Notes |
|---|---|---|---|
| pydantic | MIT | Model types | |
| numpy | BSD-3-Clause (plus bundled 0BSD, MIT, Zlib, CC0 parts) | Transforms, meshes | |
| shapely | BSD-3-Clause | Plan geometry | Its wheels bundle the GEOS library, which is LGPL-2.1. Used as a library, unmodified. |
| networkx | BSD-3-Clause | Room graph | |
| pyyaml | MIT | Config and rule files | |
| ezdxf | MIT | DXF export and import | |
| trimesh | MIT | glTF export | |
| mapbox-earcut | ISC | Polygon triangulation for trimesh | |
| pypdf | BSD-3-Clause | Exact tagged vector-PDF paths and text | Installed metadata and upstream LICENSE checked; no copyleft dependency added. |
| pillow | MIT-CMU | Rendering synthetic plans | |
| truststore | MIT | TLS certificates from the OS store for the Census geocoder client | |
| ifcopenshell | LGPL-3.0-or-later | IFC export, validation, and reading | Copyleft. Used as an unmodified library. Approved by the author, 2026-11-05. |

## External services

| Service | Used for | What is sent | Notes |
|---|---|---|---|
| U.S. Census geocoder | Address to authority, U.S. only | The address the user enters | Only on an explicit user action. |
| OpenRouter (model `deepseek/deepseek-v4.1-flash-1017`) | Plain-language explanations of findings | Each finding's check name, verdict, slot names and the quotes from its rule file. No element ids, room labels, address or numbers | Only on an explicit user action. Called with the standard library; no package added. Chosen by the author, 2026-11-23. Requires `OPENROUTER_API_KEY`. |

## Development only (never shipped)

| Package | Licence | Used for | Notes |
|---|---|---|---|
| pytest | MIT | Tests | |
| hypothesis | MPL-2.0 | Property-based tests (spec §9.7) | Weak, file-level copyleft. Test-only. Approved by the author, 2026-11-05. |
| ruff | MIT | Lint and format | |
| mypy | MIT | Type checking | |
| types-PyYAML | Apache-2.0 | Type stubs | |
| pytest-cov | MIT | Coverage gate in `make test` (90% line and branch) | Approved by the author, 2026-11-23. |
| coverage | Apache-2.0 | Coverage measurement | Installed by pytest-cov. |

## Training (milestone M3; Kaggle environment, not installed in the project)

The scripts in `training/` run on Kaggle's Python image, which already has these packages. They
are not project dependencies. Licences read from installed metadata on 2026-11-24 (local copies of
the same packages; Kaggle's versions may differ).

| Package | Licence | Used for | Notes |
|---|---|---|---|
| torch | BSD-3-Clause, with bundled Apache-2.0, BSD-2-Clause, BSL-1.0, ISC, MIT and Zlib parts | Training and inference | |
| torchvision | BSD-3-Clause | ResNet-34 encoder and its ImageNet weights | Weights downloaded at run time from download.pytorch.org. |
| matplotlib | Matplotlib licence (PSF-based, permissive) | Reliability diagram | Optional; skipped if missing. |
| kaggle | Apache-2.0 | `training/kaggle_push.py` uploads and starts runs | Command-line tool installed on the author's machine with `uv tool install kaggle`, not in the project. |

## PDF selection

The initial vector-PDF reader uses pypdf (BSD-3-Clause), recorded above. Its installed
metadata and [upstream licence](https://github.com/py-pdf/pypdf/blob/main/LICENSE)
were checked. Supported paths and text conventions are documented in
[the exact-input demo](exact-input-demo.md).
