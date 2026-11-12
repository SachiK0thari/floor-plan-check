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

## Development only (never shipped)

| Package | Licence | Used for | Notes |
|---|---|---|---|
| pytest | MIT | Tests | |
| hypothesis | MPL-2.0 | Property-based tests (spec §9.7) | Weak, file-level copyleft. Test-only. Approved by the author, 2026-11-05. |
| ruff | MIT | Lint and format | |
| mypy | MIT | Type checking | |
| types-PyYAML | Apache-2.0 | Type stubs | |

## PDF selection

The initial vector-PDF reader uses pypdf (BSD-3-Clause), recorded above. Its installed
metadata and [upstream licence](https://github.com/py-pdf/pypdf/blob/main/LICENSE)
were checked. Supported paths and text conventions are documented in
[the exact-input demo](exact-input-demo.md).
