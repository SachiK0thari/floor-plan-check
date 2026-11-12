# Multi-code results

The report keeps every source finding and group finding. Each now carries a
`regime` (`ada` or `building_code`) and a structured `citation` with code, edition,
section, URL, jurisdiction, ruleset, and effective/superseded dates. Classification
uses the originating ruleset, not a guess from the rule ID or code name.
`Report.for_regime(...)` provides a filtered view without combining verdicts.

## Governing requirements

`Report.governing_requirements` is a derived view, separate from pass/fail results.
Each row identifies an element, quantity, measurement basis, bound direction,
normalized millimetre requirement, and all governing rule IDs (including ties).
Its `source_findings` preserve both regimes' measurements, verdicts, original units,
and citations. A governing row has no new compliance verdict.

A row requires applicable sources from both regimes, verified rule status, explicit
compatible check-emitted measurement semantics, the same measured value and
uncertainty/provenance, and resolved conditions. Minimum bounds select the largest
value; maximum bounds select the smallest. Thresholds come from each check's
actual result after checked exceptions, rather than the YAML's general threshold.
Different elements, group obligations, and incompatible bases or bound directions
are never collapsed together.

The first supported scalar contract is `opening.clear_width`: `clear_opening` or
`one_active_leaf`, with a minimum bound. A new scalar check must emit its own
`MeasurementSemantics` contract. A common check name or numeric `required_mm`
field alone does not establish comparability. Corridor exceptions, circle-or-T
turning spaces, route connectivity, and maneuvering-clearance rectangles remain
separate findings; their scalar summaries cannot establish a governing bound.

`Report.governing_not_derived` (also in coverage) explains attempted comparisons
that could not be made. Missing measurements, unresolved applicability, unverified
rules, potentially relevant surfaced exceptions, uncertain exception thresholds,
and scoping assumptions block derivation. The door check recognizes that its
alteration-specific surfaced exception is irrelevant to explicitly new work;
other surfaced conditions remain unresolved. An exception-free scoping obligation
can establish applicability independently of another obligation's assumptions.
A measurement near a threshold may be `borderline` while its applicable governing
requirement is still known; both source verdicts remain unchanged.

## Adoption and provisional locations

`run` loads adoption records from the configured directory unless records are
explicitly supplied by the caller (useful for isolated tests). Local layers require
a complete selected adoption chain and project permit date. A loaded model-code
edition must match an adoption record in that chain. Missing records and adoption
facts produce `unknown`; unrelated jurisdictions or unadopted base editions are
`not_applicable`. Selecting a location does not manufacture adoption facts.

An address-proposed jurisdiction can produce **provisional** building-code findings
when its records are complete. They retain their source verdict, carry
`provisional: true`, and appear in unresolved coverage. They cannot produce a
governing requirement until the authority is confirmed. ADA findings stay separate.
No production local adoption records or code parameters are supplied by this change.
Maharashtra authority identifiers and verified rules remain separate work.

## Amendments and dates

`resolve` validates structural layering and retains the original ordered source
rules. `run` uses `ResolvedRules.for_project` to apply amendments against project
applicability and adoption status. Effective dates are inclusive; superseded dates
are exclusive. A known inapplicable replacement or deletion leaves the earlier
base rule available, subject to that base rule's own applicability. Unknown
amendment applicability blocks the target; it cannot silently reinstate a weaker
base requirement. A child amendment whose target is inactive remains unresolved,
rather than inventing a fallback to an earlier ancestor.

`Report.amendments` and coverage's `amendment_details` retain both complete rule
records, rulesets, hashes, applicability status, and explanation. An active
replacement supplies the effective finding; an active deletion supplies no
technical finding or numeric requirement. The archived base rule is not presented
as a simultaneously applicable source finding. ADA protection remains enforced
by the registry. Use `resolve` to construct production inputs so the original
amendment history is available; manually constructed `ResolvedRules` without
`source_rules` retain their caller-supplied effective rules.

Route checks select a compatible door-width dependency within their own regime.
A unique same-code/edition rule is preferred; ambiguous dependencies stay unknown
instead of depending on load order. This is conservative when several independent
building-code width rules remain active.

All multi-code tests use explicitly synthetic local requirements and adoption
records; they do not assert legal requirements for any real jurisdiction.
