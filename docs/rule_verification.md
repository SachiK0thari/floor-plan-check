# Rule verification record

This file records who has checked the rule files under `rules/` against their source text, and what each check found. The `verified_by` line in each rule file points here.

## Status

**No ADA rule has been verified by the author.** Both checks below were done by language models. They do not meet the "author-verified" requirement in the [implementation plan](IMPROVEMENT_PLAN.md); they are evidence for the author's own check, not a replacement for it.

| Check | Date | Done by | Method |
|---|---|---|---|
| First | 2026-11-05 | Claude Code (model not recorded) | Read each value from the ada.gov text. Every quote is matched to the stored snapshot by `quote_problems` in the test suite. |
| Second | 2026-11-22 | Claude Opus, run as a separate agent | Read all seven rule files and the snapshot [rules/sources/ada_2010/2010-ada-standards.txt](../rules/sources/ada_2010/2010-ada-standards.txt). It was not shown the first check's conclusions, was told not to rely on memory of the standard, and changed no files. |

The second check covered, for every rule: section numbers, each value and unit, each quote (found verbatim under the cited section), the meaning of the rule against the section, and internal consistency.

## Result of the second check

No value, unit, section number or quote mismatch was found in any file.

| Rule file | Sections, values, units, quotes | Meaning |
|---|---|---|
| `door_clear_width.yaml` | Confirmed | Notes |
| `door_maneuvering_clearance.yaml` | Confirmed | **Discrepancy (open)** |
| `toilet_room_turning_space.yaml` | Confirmed | Notes |
| `walking_surface_clear_width.yaml` | Confirmed | Notes |
| `accessible_route.yaml` | Confirmed | Notes |
| `scoping_entrances.yaml` | Confirmed | Notes |
| `scoping_room_doors.yaml` | Confirmed | Notes |

Snapshot line numbers are given in brackets.

## Open discrepancy

**`door_maneuvering_clearance.yaml`: a `fail` is reported as proof, but it is not.** The rule checks only the front-approach rows of Table 404.2.4.1 and declares `proves: fail_only`, so a `fail` stands. The side-approach rows need less clearance perpendicular to the door: 48 in for a latch-side pull [1352] and 42 in for a latch-side or hinge-side push [1351, 1353], against 60 in and 48 in from the front [1347, 1348]. A door with 48 to 59 in on the pull side therefore fails this check and may still comply. The rule's own `other-approach` exception says so, but the verdict is not softened.

This was confirmed against the snapshot table after the second check reported it. It needs a decision: either establish the approach direction, or report a front-approach failure as `borderline` or `unknown`.

## Notes that could change a verdict

These are the second model's observations. They have not been reviewed by the author.

- **`walking_surface_clear_width.yaml`**
  - The rule declares `proves: both`, but a 36 in corridor with a 180-degree turn would pass, while 403.5.2 requires 42 in approaching the turn and 48 in at it [1320].
  - The filter selects every corridor. The source applies only to walking surfaces that are part of an accessible route [1310].
  - The employee work area exception to 403.5 is not mentioned [1315].
- **`accessible_route.yaml`**
  - The paraphrase drops "which are otherwise connected by a circulation path" [496]. A room with no circulation connection should be not applicable, not a failure.
  - The exceptions paraphrase leaves out conditions on the courtroom and mezzanine exceptions and does not name the fixed-seating exception [498–500].
- **`scoping_entrances.yaml`**
  - The source counts entrances; the rule counts exterior doors. An entrance with two doors, one compliant, could be miscounted [565].
  - The two exceptions to 206.4 (altered entrances, qualified historic buildings) are not mentioned [546–547].
  - The requirement that entrance doors be on an accessible route is not encoded [545].
- **`scoping_room_doors.yaml`**
  - General exceptions that take a space out of scope, such as machinery spaces (203.5), are not recorded [435].
  - 206.5.3 (transient lodging) and 206.5.4 (residential dwelling units) are not mentioned [567–569].
- **`door_maneuvering_clearance.yaml`**
  - There is no double-leaf handling, although 404.2.2 applies 404.2.4 to one active leaf [1335].

## Notes with no effect on a verdict

- **`door_clear_width.yaml`**
  - Exception 2 to 404.2.3 (closers and stops at 78 in minimum) and the projection limits in the body of 404.2.3 are not mentioned [1336, 1339].
  - The paraphrase drops "swinging doors" and "open 90 degrees" from the measurement method [1336].
  - "The pair is not measured together" is an inference from 404.2.2, consistent with the source but not stated in it [1335].
- **`toilet_room_turning_space.yaml`**
  - The T-shape dimensions agree with each other (12 + 36 + 12 = 60 and 36 + 24 = 60).
  - The narrower knee and toe clearance limit for the T-shape in 304.3.2 is not recorded [1207].
  - The scoping-exceptions paraphrase merges two of the four exceptions to 213.2 and drops the conditions on the first [675–678].
- **All files:** the shared `effective_date` of 2012-03-15 is supported by the snapshot [42, 88].
