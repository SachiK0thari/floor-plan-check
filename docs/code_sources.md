# Code sources

One row per source of code text or code facts. `Storable` says whether verbatim text may go
into the RAG corpus. The default is **no**: store the section number, an author-written
paraphrase, the numeric requirement, and a link (docs/PROJECT_SPEC.md §3).

| Source | Publisher | Terms | Storable | Confirmed by / date |
|---|---|---|---|---|
| 2010 ADA Standards for Accessible Design | U.S. Department of Justice | U.S. government work | yes | Snapshot in `rules/sources/ada_2010/` (retrieved 2026-11-05, hashes in its SOURCE.md) |
| International Building Code (any edition) | International Code Council | Copyrighted; free to view online | no | _author to confirm_ |
| Local building code for the target jurisdiction | _TBD (configs/jurisdiction.yaml)_ | _TBD_ | no until confirmed | — |
