# 2010 ADA Standards for Accessible Design: text snapshot

| | |
|---|---|
| Publisher | U.S. Department of Justice (ADA.gov) |
| URL | https://www.ada.gov/law-and-regs/design-standards/2010-stds/ |
| Retrieved | 2026-11-05 |
| Terms | U.S. government work |
| SHA-256 of the HTML as downloaded | `a2f0dc7adef43a4ace25e5f2792b7ab83a828e56d101f2ed84cbd40c77727554` |
| SHA-256 of `2010-ada-standards.txt` | `ba3783250faec6097a728f112cac2a1e23a3e5f95edec19395e0798712f03eca` |

`2010-ada-standards.txt` is the page converted to plain text with `scripts/html_to_text.py`:
one line per paragraph, each table row on one line. Nothing else was edited, so spelling
is the source's own (it writes "Manuevering" in two table headings).

Every numeric value in `rules/ada_2010/*.yaml` carries a verbatim quote, and
`make validate-rules` (and the test suite) checks that each quote appears in this file,
under the cited section, and contains the number. To refresh the snapshot, download the
page again, rerun the script, update the hashes above, and rerun `make validate-rules`.
