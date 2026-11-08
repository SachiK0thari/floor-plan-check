"""Loading rule files, checking them against their source text, and layering rulesets.

Run as a module (``make validate-rules``) to list every rule with its status and any
problems.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from plancheck.compliance.rules import Param, Rule

RULES_DIR = Path(__file__).resolve().parent.parent.parent / "rules"
PROTECTED_RULESETS = frozenset({"ada_2010"})
"""Rulesets no other rule may amend. The ADA is a separate obligation from any building code."""

_UNIT_WORDS = {
    "in": r"inch(es)?",
    "ft": r"(feet|foot)",
    "mm": r"mm",
    "m": r"m",
    "percent": r"percent",
}


class RuleError(ValueError):
    """A rule file or a combination of rulesets is invalid."""


@dataclass(frozen=True)
class LoadedRule:
    rule: Rule
    ruleset: str
    path: Path
    sha256: str


def load_ruleset(name: str, rules_dir: Path | None = None) -> list[LoadedRule]:
    """Load ``rules/<name>/*.yaml``. A local ruleset is named ``local/<slug>``."""
    folder = (rules_dir or RULES_DIR) / name
    if not folder.is_dir():
        raise RuleError(f"ruleset '{name}' not found at {folder}")
    slug = name.removeprefix("local/") if name.startswith("local/") else None
    loaded = []
    for path in sorted(folder.glob("*.yaml")):
        raw = path.read_bytes()
        try:
            rule = Rule.model_validate(yaml.safe_load(raw))
        except ValueError as error:
            raise RuleError(f"{path}: {error}") from error
        if rule.jurisdiction != slug:
            raise RuleError(
                f"{path}: jurisdiction is {rule.jurisdiction!r} but the ruleset is '{name}'"
            )
        loaded.append(LoadedRule(rule, name, path, hashlib.sha256(raw).hexdigest()))
    return loaded


# ---------------------------------------------------------------- quotes


@cache
def _source_text(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _section_start(text: str, section: str) -> int:
    """Where the section begins in the snapshot: the first line that starts with its number."""
    match = re.search(rf"(?:^|\n){re.escape(section)} ", text)
    return match.start() if match else -1


def quote_problems(loaded: LoadedRule, rules_dir: Path | None = None) -> list[str]:
    """Ways in which the rule's quotes fail to match its source snapshot. Empty means all match.

    Each quote must appear word for word, after the start of the section it is cited
    from. A quote attached to a number must also contain that number with its unit.
    """
    rule = loaded.rule
    if rule.source_text is None:
        return []
    path = (rules_dir or RULES_DIR) / "sources" / rule.source_text
    if not path.is_file():
        return [f"source snapshot {rule.source_text} not found"]
    raw = path.read_text(encoding="utf-8")
    flat = _source_text(path)
    problems = []

    def check(label: str, quote: str | None, section: str, param: Param | None = None) -> None:
        if quote is None:
            if param is not None and rule.status == "verified":
                problems.append(f"{label}: verified value has no quote")
            return
        start = _section_start(raw, section)
        if start < 0:
            problems.append(f"{label}: section {section} not found in the source")
            return
        after = re.sub(r"\s+", " ", raw[start:])
        wanted = re.sub(r"\s+", " ", quote).strip()
        if wanted not in after:
            where = "elsewhere in the source" if wanted in flat else "nowhere in the source"
            problems.append(f"{label}: quote not found under section {section} (it is {where})")
            return
        if param is not None and param.value is not None:
            number = rf"(?<![\d./]){re.escape(f'{param.value:g}')}\s+{_UNIT_WORDS[param.unit]}"
            if not re.search(number, wanted):
                problems.append(f"{label}: quote does not contain '{param.as_written()}'")

    check("rule", rule.quote, rule.section)
    for name, param in rule.requirement.items():
        check(name, param.quote, param.section or rule.section, param)
    for exception in rule.exceptions:
        section = exception.section or rule.section
        check(exception.id, exception.quote, section)
        for name, param in exception.params.items():
            check(f"{exception.id}.{name}", param.quote, param.section or section, param)
    return problems


# ---------------------------------------------------------------- layering


@dataclass
class ResolvedRules:
    """The effective rule list for an ordered list of rulesets."""

    rulesets: list[str]
    rules: list[LoadedRule] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # amendments applied, for the report
    not_runnable: list[tuple[str, str]] = field(default_factory=list)  # (rule id, reason)

    def get(self, rule_id: str) -> LoadedRule:
        return next(r for r in self.rules if r.rule.id == rule_id)

    @property
    def runnable(self) -> list[LoadedRule]:
        skipped = {rule_id for rule_id, _ in self.not_runnable}
        return [r for r in self.rules if r.rule.id not in skipped]

    def fingerprint(self) -> list[tuple[str, str]]:
        """(rule id, file hash) pairs, stored with a check run so it can be reproduced."""
        return [(r.rule.id, r.sha256) for r in self.rules]


def resolve(rulesets: Sequence[str], rules_dir: Path | None = None) -> ResolvedRules:
    """Combine rulesets, in order, into one effective rule list.

    A rule may amend a rule from an earlier ruleset: ``replace`` swaps it out, ``delete``
    removes it. Because a rule can only amend something earlier in the order, amendment
    chains resolve in order and cannot form a cycle.
    """
    resolved = ResolvedRules(rulesets=list(rulesets))
    effective: dict[str, LoadedRule] = {}
    seen: set[str] = set()
    for name in rulesets:
        incoming = load_ruleset(name, rules_dir)
        targets: dict[str, str] = {}
        additions: list[LoadedRule] = []
        for loaded in incoming:
            rule = loaded.rule
            if rule.id in seen:
                raise RuleError(f"rule id '{rule.id}' is defined more than once")
            seen.add(rule.id)
            if rule.amends is None:
                additions.append(loaded)
                continue
            if rule.amends.rule in targets:
                raise RuleError(
                    f"{rule.id} and {targets[rule.amends.rule]} both amend {rule.amends.rule}"
                )
            target = effective.get(rule.amends.rule)
            if target is None:
                raise RuleError(
                    f"{rule.id} amends '{rule.amends.rule}', which is not in an earlier ruleset"
                )
            if target.ruleset in PROTECTED_RULESETS:
                raise RuleError(
                    f"{rule.id} tries to amend {target.rule.id}; {target.ruleset} rules "
                    "cannot be amended"
                )
            targets[target.rule.id] = rule.id
            del effective[target.rule.id]
            if rule.amends.mode == "replace":
                additions.append(loaded)
                resolved.notes.append(f"{rule.id} replaces {target.rule.id} ({rule.code})")
            else:
                resolved.notes.append(f"{rule.id} deletes {target.rule.id} ({rule.code})")
        for loaded in additions:
            effective[loaded.rule.id] = loaded
    resolved.rules = list(effective.values())
    for loaded in resolved.rules:
        missing = loaded.rule.null_params()
        if missing:
            resolved.not_runnable.append((loaded.rule.id, f"values not filled in: {missing}"))
    return resolved


# ---------------------------------------------------------------- command line


def available_rulesets(rules_dir: Path | None = None) -> list[str]:
    root = rules_dir or RULES_DIR
    names = [
        p.name for p in sorted(root.iterdir()) if p.is_dir() and p.name not in ("local", "sources")
    ]
    local = root / "local"
    if local.is_dir():
        names += [f"local/{p.name}" for p in sorted(local.iterdir()) if p.is_dir()]
    return [name for name in names if any((root / name).glob("*.yaml"))]


def main() -> int:
    """List every rule; exit non-zero if a rule file is invalid or a quote does not match."""
    failed = False
    names = available_rulesets()
    for name in names:
        print(f"\n{name}")
        try:
            rules = load_ruleset(name)
        except RuleError as error:
            print(f"  INVALID  {error}")
            failed = True
            continue
        for loaded in rules:
            rule = loaded.rule
            print(f"  {rule.status:<8} {rule.id}  ({rule.section})")
            for missing in rule.null_params():
                print(f"           not filled in: {missing}")
            for problem in quote_problems(loaded):
                print(f"           QUOTE MISMATCH  {problem}")
                failed = True
    try:
        resolve(names)
    except RuleError as error:
        print(f"\nLAYERING  {error}")
        failed = True
    print("\nproblems found" if failed else "\nall rule files are valid and every quote matches")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
