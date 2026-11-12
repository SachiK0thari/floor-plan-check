"""Seeded, fixture-conditioned sensitivity budgets; not extraction performance claims."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

from plancheck import __version__
from plancheck.compliance.artifacts import _engine_identity
from plancheck.compliance.checks import CHECK_FUNCTIONS
from plancheck.compliance.context import CheckContext
from plancheck.compliance.registry import load_ruleset
from plancheck.compliance.rules import Rule
from plancheck.compliance.verdict import Verdict, restrict
from plancheck.evaluation.plans import corridor_plan, transform_model
from plancheck.evaluation.validate import wilson
from plancheck.model.types import Measured

GEOMETRY_SIGMAS = (0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0)
SCALE_SIGMAS = (0.0, 0.0001, 0.0005, 0.001, 0.0025, 0.005, 0.01)


def study(trials: int = 200, seed: int = 20261109) -> dict[str, Any]:
    if trials < 1:
        raise ValueError("trials must be positive")
    rules = {
        r.rule.check: r
        for r in load_ruleset("ada_2010")
        if r.rule.kind == "technical" and r.rule.check is not None
    }
    width_limit = rules["opening_clear_width"].rule.requirement["min_clear_width"].mm
    corridor_limit = rules["corridor_min_width"].rule.requirement["min_clear_width"].mm
    turning_limit = rules["turning_space"].rule.requirement["circle_diameter"].mm
    maneuver_limit = rules["door_maneuvering_clearance"].rule.requirement["pull_perpendicular"].mm
    rows = []
    rng = random.Random(seed)
    for check in sorted(rules):
        loaded = rules[check]
        rule = loaded.rule
        margins = (-25.0, 25.0) if rule.proves == "both" else (-25.0,)
        for margin in margins:
            base_width = (
                corridor_limit + margin
                if check == "corridor_min_width"
                else turning_limit + margin
                if check == "turning_space"
                else maneuver_limit + margin
                if check == "door_maneuvering_clearance"
                else 2000.0
            )
            base_clear = (
                width_limit + margin
                if check in ("opening_clear_width", "accessible_route_exists")
                else 900.0
            )

            def evaluate(
                sigma: float,
                relative: float,
                noisy: bool,
                *,
                base_width: float = base_width,
                base_clear: float = base_clear,
                check: str = check,
                rule: Rule = rule,
            ) -> Verdict:
                width = base_width + (rng.gauss(0, sigma) if noisy else 0)
                clear = base_clear + (rng.gauss(0, sigma) if noisy else 0)
                model = corridor_plan(
                    width, clear, room_type="bathroom" if check == "turning_space" else "corridor"
                )
                if noisy and sigma:
                    walls = [
                        w.model_copy(
                            update={
                                "start": (
                                    w.start[0] + rng.gauss(0, sigma),
                                    w.start[1] + rng.gauss(0, sigma),
                                ),
                                "end": (
                                    w.end[0] + rng.gauss(0, sigma),
                                    w.end[1] + rng.gauss(0, sigma),
                                ),
                                "thickness": w.thickness.model_copy(update={"sigma_mm": sigma}),
                            }
                        )
                        for w in model.walls
                    ]
                    openings = [
                        o.model_copy(
                            update={
                                "clear_width": Measured(
                                    value_mm=clear, sigma_mm=sigma, source="geometry"
                                )
                            }
                        )
                        for o in model.openings
                    ]
                    model = model.model_copy(update={"walls": walls, "openings": openings})
                if noisy and relative:
                    model = transform_model(model, factor=1 + rng.gauss(0, relative))
                    model = model.model_copy(update={"scale_rel_sigma": relative})
                ctx = CheckContext(
                    k=2, clear_width_deductions={}, door_rule=rules["opening_clear_width"].rule
                )
                element = (
                    model.openings[0]
                    if rule.selection and rule.selection.element == "opening"
                    else model.rooms[0]
                )
                outcome = CHECK_FUNCTIONS[check](model, rule, element, ctx)
                return restrict(outcome.verdict, rule.proves or "both")

            baseline = evaluate(0, 0, False)
            if baseline not in (Verdict.PASS, Verdict.FAIL):
                raise ValueError(f"{check} fixture has no decisive baseline: {baseline}")
            for mode, settings in (("geometry", GEOMETRY_SIGMAS), ("scale", SCALE_SIGMAS)):
                for setting in settings:
                    sigma, relative = (setting, 0) if mode == "geometry" else (0, setting)
                    counts: Counter[str] = Counter()
                    for _ in range(trials):
                        try:
                            counts[str(evaluate(sigma, relative, True))] += 1
                        except ValueError:
                            counts["invalid_geometry"] += 1
                    matched = counts[str(baseline)]
                    low, high = wilson(matched, trials)
                    rows.append(
                        {
                            "check": check,
                            "rule_id": rule.id,
                            "rule_sha256": loaded.sha256,
                            "margin_mm": margin,
                            "mode": mode,
                            "sigma_mm": sigma,
                            "scale_sigma": relative,
                            "baseline": str(baseline),
                            "matched": matched,
                            "trials": trials,
                            "counts": dict(counts),
                            "retention": matched / trials,
                            "wilson_95": [low, high],
                            "qualifies": low >= 0.95,
                        }
                    )
    summaries = []
    for check in sorted(rules):
        budgets = {}
        for mode, settings in (("geometry", GEOMETRY_SIGMAS), ("scale", SCALE_SIGMAS)):
            accepted = None
            for setting in settings:
                sampled = [
                    r
                    for r in rows
                    if r["check"] == check
                    and r["mode"] == mode
                    and (r["sigma_mm"] if mode == "geometry" else r["scale_sigma"]) == setting
                ]
                if not all(r["qualifies"] for r in sampled):
                    break
                accepted = setting
            budgets[mode] = accepted
        permitted_sigma = budgets["geometry"]
        pitch = (
            permitted_sigma * math.sqrt(12)
            if permitted_sigma is not None and permitted_sigma > 0
            else None
        )
        summaries.append(
            {
                "check": check,
                "geometry_sigma_mm": permitted_sigma,
                "scale_sigma": budgets["scale"],
                "max_world_mm_per_pixel": pitch,
                "minimum_dpi_at_1_100": math.ceil(25.4 * 100 / pitch) if pitch else None,
            }
        )
    return {
        "schema_version": 1,
        "engine_version": __version__,
        "engine": _engine_identity().model_dump(mode="json"),
        "seed": seed,
        "trials_per_setting": trials,
        "status": "preliminary_synthetic_not_author_verified",
        "criterion": (
            "Wilson 95% lower bound >= 95% unchanged decisive verdicts, contiguous sampled prefix"
        ),
        "noise_model": (
            "independent Gaussian clear-width/net-floor-width errors, "
            "wall-endpoint jitter; reported sigma proxy; "
            "isotropic scale errors studied separately"
        ),
        "limits": (
            "Fixture-conditioned at +/-25 mm margins where the check can prove a verdict; "
            "not a universal extraction specification. "
            "Pixel conversion assumes uniform quantization only."
        ),
        "summaries": summaries,
        "samples": rows,
    }


def write_budget(result: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "accuracy-budget.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Preliminary synthetic accuracy budget",
        "",
        result["limits"],
        "",
        result["criterion"],
        "",
        f"Seed: {result['seed']}; trials per setting: {result['trials_per_setting']}. "
        "Invalid geometry counts as changed, not discarded.",
        "",
        "| Check | Geometry sigma (mm) | Relative scale sigma | "
        "Max world mm/pixel | Min DPI at 1:100 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in result["summaries"]:

        def show(value: float | None) -> str:
            return f"{value:g}" if value is not None else "not established"

        lines.append(
            "| "
            + " | ".join(
                [
                    row["check"],
                    show(row["geometry_sigma_mm"]),
                    show(row["scale_sigma"]),
                    show(row["max_world_mm_per_pixel"]),
                    show(row["minimum_dpi_at_1_100"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "Zero is a measured grid result; it does not imply an achievable finite DPI. "
        "A missing budget means this study did not establish one.",
        "",
        "Full counts, verdict transitions, rule hashes and confidence intervals are in "
        "accuracy-budget.json. Geometry and scale were not perturbed jointly.",
        "",
        "Author-reviewed plans, local-code checks, and calibrated extraction error distributions "
        "remain required before using these as product upload thresholds.",
    ]
    (folder / "accuracy-budget.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--output", type=Path, default=Path("eval/reports"))
    args = parser.parse_args()
    write_budget(study(args.trials, args.seed), args.output)


if __name__ == "__main__":
    main()
