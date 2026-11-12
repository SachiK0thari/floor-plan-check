"""Readable reports rendered from saved run artifacts, with escaped drawing text."""

from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import urlsplit

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.compliance.results import Finding

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


def report_text(artifact: CheckRunArtifact) -> str:
    report = artifact.report
    coverage = report.coverage
    checked_count = sum(sum(counts.values()) for counts in coverage.get("checked", {}).values())
    summary = [
        "Coverage summary (read before interpreting findings)",
        f"Executed technical findings: {checked_count}",
        f"Excluded records: {len(coverage.get('excluded', []))}; "
        f"unresolved/review records: {len(coverage.get('unresolved', []))}",
        "Unimplemented provisions: "
        + (", ".join(coverage.get("not_implemented", [])) or "none in selected rulesets"),
        "Not visible on a plan: " + "; ".join(coverage.get("not_visible_on_a_plan", [])),
        "These counts cover the selected implemented provisions only, not the entire code.",
    ]
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
    return "\n\n".join(sections) + "\n"


def export_report(artifact: CheckRunArtifact, path: Path) -> Path:
    """HTML is self-contained and printable; .md/.txt produce readable plain text."""
    text = report_text(artifact)
    if path.suffix.lower() == ".html":
        body = html.escape(text)
        links = []
        for url in sorted(
            {
                f.citation.source_url
                for f in artifact.report.findings
                if f.citation and f.citation.source_url
            }
        ):
            if urlsplit(url).scheme in ("http", "https"):
                escaped = html.escape(url, quote=True)
                links.append(f'<li><a href="{escaped}" rel="noreferrer">{escaped}</a></li>')
        references = "<nav><p>Source links</p><ul>" + "".join(links) + "</ul></nav>"
        text = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            "<title>PlanCheck assessment</title><style>body{max-width:1100px;margin:2em auto;"
            "padding:1em;font:16px/1.5 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "@media print{body{font-size:10pt}}</style><main><pre>"
            + body
            + "</pre>"
            + references
            + "</main></html>"
        )
    elif path.suffix.lower() not in (".md", ".txt"):
        raise ValueError("report format must be .html, .md, or .txt")
    path.write_text(text, encoding="utf-8")
    return path
