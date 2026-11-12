# Author review worksheet

Status: pending author review. These are analytic synthetic fixtures, not an
independent CAD evaluation set.

1. Run `make demo` and inspect each source DXF/PDF under `out/demo/` alongside the
   project-context JSON. The model construction is in
   `plancheck/evaluation/plans.py`; compare it with the actual CAD vectors and
   dimensions before looking at generated findings.
2. Work out each selected ADA rule independently, using the verified rule YAML
   and its cited official source. Record both the measured value and applicability
   reasoning, including uncertainty and any exceptions. For maneuvering clearance,
   check the pull/push geometry and the stated assumed approach; a door width pass
   does not establish its maneuvering clearance.
3. Check every per-element and group entry in `expected.yaml`. Preserve unknown
   when an input/proof is absent and not_applicable for resolved exclusions.
   Investigate differences rather than copying the engine's output into expected
   results. The `wide` fixture describes corridor width, not whole-plan compliance.
4. Record the reviewer, date, independent calculations, and corrections in a review
   note. Only after that review, update the manifest's status to `author_verified`
   and set `reviewed_by`, referencing the review note.
5. Run `uv run python -m plancheck.evaluation.validate --require-reviewed`.

A synthetic round trip is not an independent CAD/PDF test. Draw the specification's
CAD evaluation set separately with deliberate violations and registration fiducials;
verify plotted PDFs from the actual CAD workflow. Found/independently annotated
plans and verified Maharashtra cases must be reported separately.
