# Preliminary synthetic accuracy budget

Fixture-conditioned at +/-25 mm margins where the check can prove a verdict; not a universal extraction specification. Pixel conversion assumes uniform quantization only.

Wilson 95% lower bound >= 95% unchanged decisive verdicts, contiguous sampled prefix

Seed: 20261109; trials per setting: 200. Invalid geometry counts as changed, not discarded.

| Check | Geometry sigma (mm) | Relative scale sigma | Max world mm/pixel | Min DPI at 1:100 |
|---|---:|---:|---:|---:|
| accessible_route_exists | 5 | 0.01 | 17.3205 | 147 |
| corridor_min_width | 2 | 0.005 | 6.9282 | 367 |
| door_maneuvering_clearance | 10 | 0.005 | 34.641 | 74 |
| opening_clear_width | 5 | 0.01 | 17.3205 | 147 |
| turning_space | 2 | 0.005 | 6.9282 | 367 |

Zero is a measured grid result; it does not imply an achievable finite DPI. A missing budget means this study did not establish one.

Full counts, verdict transitions, rule hashes and confidence intervals are in accuracy-budget.json. Geometry and scale were not perturbed jointly.

Author-reviewed plans, local-code checks, and calibrated extraction error distributions remain required before using these as product upload thresholds.
