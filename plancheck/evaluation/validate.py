"""Compare every fixture finding against analytic expectations; record pending author review."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import yaml

from plancheck.compliance.engine import Report, run
from plancheck.compliance.registry import resolve
from plancheck.evaluation.plans import review_plans, transform_model


def signatures(report: Report) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {"findings": {}, "groups": {}}
    for group, findings in (("findings", report.findings), ("groups", report.group_findings)):
        for f in findings:
            key = f.group if group == "groups" else ",".join(f.element_ids) or "project"
            result[group].setdefault(f.rule_id, {})[key or "project"] = str(f.verdict)
    return result


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("confidence interval needs observations")
    z = 1.959963984540054
    p = successes / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0, center - half), min(1, center + half)


def evaluate(
    expected_path: Path, report_path: Path, require_reviewed: bool = False
) -> dict[str, Any]:
    expected = yaml.safe_load(expected_path.read_text())
    if require_reviewed and (
        expected.get("review_status") != "author_verified" or not expected.get("reviewed_by")
    ):
        raise ValueError(
            "author hand-checks are still pending; analytic fixtures are not accepted goldens"
        )
    details = []
    for name, model in review_plans().items():
        wanted = expected["plans"][name]
        for variant, transformed in [
            ("original", model),
            ("translated", transform_model(model, dx=1234, dy=-567)),
            ("rotated", transform_model(model, angle=37)),
            ("mirrored", transform_model(model, mirror=True)),
        ]:
            actual = signatures(run(transformed, resolve(["ada_2010"])))
            details.append(
                {
                    "plan": name,
                    "variant": variant,
                    "matches": actual == wanted,
                    "actual": actual,
                    "expected": wanted,
                }
            )
    passed = sum(d["matches"] for d in details)
    low, high = wilson(passed, len(details))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# Analytic model validation\n\n"
        f"Review: {expected['review_status']}; independent author review is required.\n\n"
        f"Unit of analysis: complete plan/transform signature; correlated synthetic fixtures.\n\n"
        f"Matched {passed}/{len(details)} ({passed / len(details):.1%}; "
        f"Wilson 95% interval {low:.1%}-{high:.1%}).\n\n"
        + "\n".join(
            f"- {d['plan']} / {d['variant']}: {'match' if d['matches'] else 'MISMATCH'}"
            for d in details
        )
        + "\n"
    )
    if passed != len(details):
        raise ValueError("evaluation verdict mismatch; inspect actual signatures")
    return {"review_status": expected["review_status"], "cases": details}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    evaluate(
        Path("eval/compliance/expected.yaml"),
        Path("eval/reports/model-validation.md"),
        args.require_reviewed,
    )


if __name__ == "__main__":
    main()
