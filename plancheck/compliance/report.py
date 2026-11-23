"""Readable reports rendered from saved run artifacts, with escaped drawing text."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.compliance.results import Finding
from plancheck.export.svg import plan_svg_element

if TYPE_CHECKING:
    from plancheck.rag.explain import ExplanationRun

EXPLANATION_LABEL = (
    "Explanation written by a language model. PlanCheck filled in every value and "
    "citation; the model did not decide the verdict."
)

DISCLAIMER = (
    "Design-assist tool, not a code review. No findings does not establish compliance. "
    "Verify results against the code adopted for the project. Unchecked provisions and "
    "information not visible on a plan remain outside this assessment. "
    "Measurement uncertainty is included; no construction tolerance is applied."
)


def finding_description(finding: Finding) -> str:
    measured = (
        f"{finding.measured.value_mm:g} +/- {finding.measured.sigma_mm:g} mm "
        f"(standard uncertainty; source: {finding.measured.source})"
        if finding.measured is not None
        else "not measured"
    )
    citation = finding.citation
    source = (
        f"{citation.code}, edition {citation.edition}, section {citation.section}; "
        f"jurisdiction: {citation.jurisdiction or 'base/reference'}; "
        f"{citation.source_url or 'URL unavailable'}"
        if citation
        else f"{finding.code}, section {finding.section}"
    )
    return "\n".join(
        [
            f"{finding.title} [{finding.verdict}]"
            + (" (PROVISIONAL)" if finding.provisional else ""),
            f"Rule: {finding.rule_id}; elements: "
            f"{', '.join(finding.element_ids) or 'project-wide'}",
            f"Measurement: {measured}",
            f"Requirement: {finding.required or 'not determined'}",
            f"Reason: {finding.reason or 'none recorded'}",
            f"Citation: {source}",
            "Obligations: " + ("; ".join(finding.obligations) or "none"),
            "Unresolved exceptions: " + (", ".join(finding.surfaced_exceptions) or "none surfaced"),
        ]
    )


def explanation_summary(explanations: ExplanationRun) -> str:
    return (
        f"{len(explanations.explanations)} findings explained by {explanations.model_id} "
        f"through {explanations.service}; {explanations.outputs_requested} model outputs "
        f"requested, {len(explanations.rejections)} rejected by the validator, "
        f"{len(explanations.unexplained)} findings left unexplained."
    )


def report_text(artifact: CheckRunArtifact, explanations: ExplanationRun | None = None) -> str:
    report = artifact.report
    coverage = report.coverage
    summary = ["Coverage summary (read before interpreting findings)", *coverage_summary(artifact)]
    sections = [
        "PlanCheck assessment",
        DISCLAIMER,
        "\n".join(summary),
        f"Run: {artifact.created_at.isoformat()}; engine {artifact.engine.version}; "
        f"Git {artifact.engine.git_sha or 'unavailable'}",
        f"Source digest: {artifact.engine.source_sha256}; "
        f"lockfile SHA-256: {artifact.dependency_lockfile_sha256}",
        "Project context\n" + artifact.model.project.model_dump_json(indent=2),
    ]
    if artifact.model.warnings:
        sections.append("Drawing review notes\n" + "\n".join(artifact.model.warnings))
    if artifact.model.location_extraction is not None:
        location = artifact.model.location_extraction
        sections.append(f"Drawing location hints (UNCONFIRMED): {location.status}")
        for candidate in location.candidates:
            positions = "; ".join(
                f"{e.source}, page {e.page}, layout {e.layout}, "
                f"anchor {e.anchor} ({e.coordinate_space})"
                for e in candidate.evidence
            )
            sections.append(f"{candidate.field}: {candidate.value}\nEvidence: {positions}")
        sections.extend(location.notes)
    for regime in ("ada", "building_code"):
        sections.append(f"Findings: {regime}")
        sections.extend(finding_description(f) for f in report.for_regime(regime))
    sections.append("Group obligations")
    sections.extend(finding_description(f) for f in report.group_findings)
    sections.append("Governing requirements (derived, source findings retained)")
    for item in report.governing_requirements:
        sections.append(
            f"{item.element_id}: {item.quantity} {item.relation} {item.required}; "
            f"sources: {', '.join(item.governing_rule_ids)}; {item.reason}"
        )
    sections.append("Comparisons not derived")
    sections.extend(
        f"{item.element_id}, {item.quantity}: {item.reason}; {', '.join(item.rule_ids)}"
        for item in report.governing_not_derived
    )
    sections.append("Coverage, missing inputs, exceptions, and unchecked provisions")
    for rule_id, counts in coverage.get("checked", {}).items():
        sections.append(f"Checked {rule_id}: {counts}")
    for category in ("excluded", "unresolved"):
        for item in coverage.get(category, []):
            elements = ", ".join(item["element_ids"]) or "project-wide"
            sections.append(f"{category}: {item['rule_id']} / {elements}: {item['reason']}")
    for rule_id, reason in coverage.get("not_runnable", []):
        sections.append(f"Not runnable: {rule_id}: {reason}")
    for item in coverage.get("surfaced_exceptions", []):
        sections.append(
            f"Exceptions: {item['rule_id']} / {item['element_ids']}: {item['exceptions']}"
        )
    sections.extend(coverage.get("notes", []))
    sections.append("Amendment audit")
    for amendment in report.amendments:
        original = amendment.amended_rule
        replacement = amendment.amending_rule
        sections.append(
            f"{amendment.status}: {replacement.id} -> {original.id}: {amendment.reason}\n"
            f"Original: {original.code}, {original.edition}, {original.section}; "
            f"{original.source_url}\n"
            f"Amendment: {replacement.code}, {replacement.edition}, {replacement.section}; "
            f"{replacement.source_url}"
        )
    if explanations is not None:
        sections.append("Explanations (not part of any verdict)")
        sections.append(EXPLANATION_LABEL + " " + explanation_summary(explanations))
        sections.extend(
            f"Finding {item.finding} ({item.rule_id}; {', '.join(item.element_ids)}): {item.text}"
            for item in explanations.explanations
        )
    return "\n\n".join(sections) + "\n"


VERDICTS = {
    "fail": ("\u2715", "Fail"),
    "borderline": ("!", "Borderline"),
    "unknown": ("?", "Unknown"),
    "pass": ("\u2713", "Pass"),
    "not_applicable": ("\u2013", "Not applicable"),
}
"""Each verdict's symbol and label. Reports mark a verdict with both, not with colour alone."""

REGIMES = {"ada": "ADA", "building_code": "Building code"}

_CSS = (
    "body{max-width:1200px;margin:2em auto;padding:0 1em;font:15px/1.5 system-ui,sans-serif;"
    "color:#20372f}h1{font-size:26px}h2{font-size:19px;margin-top:2em}"
    ".disclaimer{background:#fff6dd;border:1px solid #e3cf8f;padding:12px;border-radius:6px}"
    ".chips{display:flex;gap:8px;flex-wrap:wrap;padding:0;list-style:none}"
    ".chip{border:1px solid currentColor;border-radius:14px;padding:2px 10px;white-space:nowrap}"
    ".v-fail{color:#b3261e}.v-borderline{color:#8a5a00}.v-unknown{color:#4f5d75}"
    ".v-pass{color:#1a7f37}.v-not_applicable{color:#6b7a72}"
    ".plan{border:1px solid #d5dfd5;border-radius:6px;padding:8px;background:#fff}"
    ".pc-plan{width:100%;height:auto;max-height:80vh}"
    "table{border-collapse:collapse;width:100%;font-size:14px}"
    "th,td{text-align:left;padding:8px;border-bottom:1px solid #d5dfd5;vertical-align:top}"
    "td{color:#20372f}td strong{white-space:nowrap}tr:target{background:#fff6dd}"
    ".wrap{overflow-x:auto}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer}"
    ".ai{margin-top:6px;padding:6px 8px;border-left:3px solid #7a6fb0;background:#f5f3fb}"
    ".ai small{display:block;color:#5b5480}"
    "@media print{body{font-size:10pt}details{display:none}}"
)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, {k.rstrip("_"): v for k, v in attrs.items()})
    element.text = text
    return element


def _number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def measurement_text(finding: Finding) -> str:
    """The measured value in millimetres with inches alongside, and its uncertainty."""
    if finding.measured is None:
        return "not measured"
    measured = finding.measured
    return (
        f"{_number(measured.value_mm)} mm ({measured.value_mm / 25.4:.2f} in) "
        f"\u00b1 {_number(measured.sigma_mm)} mm"
    )


def requirement_text(finding: Finding) -> str:
    """The requirement as written in the source, with the metric value alongside."""
    if finding.required is None:
        return "not determined"
    if finding.required_mm is None:
        return finding.required
    return f"{finding.required} ({_number(finding.required_mm)} mm)"


def _safe_url(url: str | None) -> str | None:
    return url if url and urlsplit(url).scheme in ("http", "https") else None


def _verdict_cell(row: ET.Element, finding: Finding) -> None:
    verdict = str(finding.verdict)
    symbol, label = VERDICTS[verdict]
    cell = _sub(row, "td", class_=f"v-{verdict}")
    _sub(cell, "strong", f"{symbol} {label}")
    if finding.provisional:
        _sub(cell, "div", "PROVISIONAL")


def _findings_table(
    parent: ET.Element,
    rows: Sequence[tuple[int | None, Finding]],
    element_title: str,
    explanations: ExplanationRun | None = None,
) -> None:
    wrap = _sub(parent, "div", class_="wrap")
    table = _sub(wrap, "table")
    head = _sub(_sub(table, "thead"), "tr")
    for title in (
        "#",
        "Verdict",
        element_title,
        "Check",
        "Measured \u00b1 standard uncertainty",
        "Required",
        "Citation",
        "Notes",
    ):
        _sub(head, "th", title)
    body = _sub(table, "tbody")
    for number, finding in rows:
        row = _sub(body, "tr")
        cell = _sub(row, "td")
        if number is not None:
            row.set("id", f"pc-row-{number}")
            _sub(cell, "a", str(number), href=f"#pc-f{number}", title="Show on the plan")
        _verdict_cell(row, finding)
        _sub(row, "td", finding.group or ", ".join(finding.element_ids) or "project-wide")
        _sub(row, "td", finding.title)
        _sub(row, "td", measurement_text(finding))
        _sub(row, "td", requirement_text(finding))
        cite = _sub(row, "td")
        citation = finding.citation
        label = (
            f"{citation.code} {citation.edition}, \u00a7{citation.section}"
            if citation
            else f"{finding.code}, \u00a7{finding.section}"
        )
        url = _safe_url(citation.source_url) if citation else None
        if url:
            _sub(cite, "a", label, href=url, rel="noreferrer")
        else:
            cite.text = label
        notes = _sub(row, "td")
        lines = [finding.reason] if finding.reason else []
        lines += [f"Exception not checked: {name}" for name in finding.surfaced_exceptions]
        lines += [f"Tested because: {why}" for why in finding.obligations]
        for line in lines:
            _sub(notes, "div", line)
        explained = (
            explanations.for_finding(number)
            if explanations is not None and number is not None
            else None
        )
        if explained is not None:
            box = _sub(notes, "div", class_="ai")
            _sub(box, "small", "Explanation (language model)")
            _sub(box, "span", explained.text)


def coverage_summary(artifact: CheckRunArtifact) -> list[str]:
    coverage = artifact.report.coverage
    checked_count = sum(sum(counts.values()) for counts in coverage.get("checked", {}).values())
    return [
        f"Executed technical findings: {checked_count}",
        f"Excluded records: {len(coverage.get('excluded', []))}; "
        f"unresolved/review records: {len(coverage.get('unresolved', []))}",
        "Unimplemented provisions: "
        + (", ".join(coverage.get("not_implemented", [])) or "none in selected rulesets"),
        "Not visible on a plan: " + "; ".join(coverage.get("not_visible_on_a_plan", [])),
        "These counts cover the selected implemented provisions only, not the entire code.",
    ]


def report_html(artifact: CheckRunArtifact, explanations: ExplanationRun | None = None) -> str:
    """A self-contained, printable page: summary, the plan with findings, then tables.

    Every string from the drawing or the project goes in as element text, so it is escaped.
    The complete text record follows the tables, so nothing in ``report_text`` is lost.
    """
    report = artifact.report
    numbered = list(enumerate(report.findings, start=1))
    page = ET.Element("html", {"lang": "en"})
    head = _sub(page, "head")
    _sub(head, "meta", charset="utf-8")
    _sub(head, "meta", name="viewport", content="width=device-width,initial-scale=1")
    _sub(head, "title", "PlanCheck assessment")
    _sub(head, "style", _CSS)
    main = _sub(_sub(page, "body"), "main")
    _sub(main, "h1", "PlanCheck assessment")
    _sub(main, "p", DISCLAIMER, class_="disclaimer")

    _sub(main, "h2", "Summary")
    counts = Counter(str(finding.verdict) for finding in report.findings)
    chips = _sub(main, "ul", class_="chips")
    for verdict, (symbol, label) in VERDICTS.items():
        if counts[verdict]:
            _sub(chips, "li", f"{symbol} {label}: {counts[verdict]}", class_=f"chip v-{verdict}")
    summary = _sub(main, "ul")
    for line in coverage_summary(artifact):
        _sub(summary, "li", line)
    for note in report.coverage.get("notes", []):
        _sub(summary, "li", str(note))
    if explanations is not None:
        _sub(summary, "li", EXPLANATION_LABEL + " " + explanation_summary(explanations))
    _sub(
        main,
        "p",
        f"Run {artifact.created_at.isoformat()}; engine {artifact.engine.version}; "
        f"Git {artifact.engine.git_sha or 'unavailable'}; rulesets: "
        f"{', '.join(artifact.rulesets)}.",
    )

    if artifact.model.walls:
        _sub(main, "h2", "Plan")
        _sub(
            main,
            "p",
            "Solid red with a number: fail. Dashed amber with a number: borderline. "
            "Dotted grey: checked, but the result is unknown. Thin green: pass. "
            "A number on the plan opens its row below; a row's number shows it on the plan.",
        )
        _sub(main, "div", class_="plan").append(plan_svg_element(artifact.model, report))

    for regime, title in REGIMES.items():
        rows = [(n, f) for n, f in numbered if f.regime == regime]
        if not rows:
            continue
        # Problems first; a finding keeps its number, which is its place in the run.
        order = list(VERDICTS)
        shown = sorted(
            ((n, f) for n, f in rows if str(f.verdict) != "not_applicable"),
            key=lambda row: order.index(str(row[1].verdict)),
        )
        hidden = [(n, f) for n, f in rows if str(f.verdict) == "not_applicable"]
        _sub(main, "h2", f"Findings: {title}")
        if shown:
            _findings_table(main, shown, "Element", explanations)
        if hidden:
            details = _sub(main, "details")
            _sub(details, "summary", f"Not applicable ({len(hidden)})")
            _findings_table(details, hidden, "Element")

    if report.group_findings:
        _sub(main, "h2", "Group obligations")
        _findings_table(main, [(None, f) for f in report.group_findings], "Group")

    if report.governing_requirements:
        _sub(main, "h2", "Governing requirements (derived; source findings retained)")
        table = _sub(_sub(main, "div", class_="wrap"), "table")
        head_row = _sub(_sub(table, "thead"), "tr")
        for title in ("Element", "Quantity", "Required", "Governing rules", "Reason"):
            _sub(head_row, "th", title)
        body = _sub(table, "tbody")
        for item in report.governing_requirements:
            row = _sub(body, "tr")
            _sub(row, "td", item.element_id)
            _sub(row, "td", f"{item.quantity} ({item.relation})")
            _sub(row, "td", f"{item.required} ({_number(item.required_mm)} mm)")
            _sub(row, "td", ", ".join(item.governing_rule_ids))
            _sub(row, "td", item.reason)

    record = _sub(main, "details")
    _sub(record, "summary", "Full text record: coverage, missing inputs, exceptions, audit")
    _sub(record, "pre", report_text(artifact, explanations))

    links = sorted(
        {
            url
            for finding in report.findings
            if finding.citation and (url := _safe_url(finding.citation.source_url))
        }
    )
    nav = _sub(main, "nav")
    _sub(nav, "p", "Source links")
    listing = _sub(nav, "ul")
    for url in links:
        _sub(_sub(listing, "li"), "a", url, href=url, rel="noreferrer")
    return "<!doctype html>" + ET.tostring(page, encoding="unicode", method="html")


def export_report(
    artifact: CheckRunArtifact, path: Path, explanations: ExplanationRun | None = None
) -> Path:
    """HTML is self-contained and printable; .md/.txt produce readable plain text."""
    suffix = path.suffix.lower()
    if suffix == ".html":
        text = report_html(artifact, explanations)
    elif suffix in (".md", ".txt"):
        text = report_text(artifact, explanations)
    else:
        raise ValueError("report format must be .html, .md, or .txt")
    path.write_text(text, encoding="utf-8")
    return path
