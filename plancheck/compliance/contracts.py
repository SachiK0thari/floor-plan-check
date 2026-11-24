"""What each check and scoping function needs from a rule file (review items A1 and A6).

A check reads its parameters by name and can prove only so much from geometry. Both facts
are declared here, next to the function, so the registry can reject a rule file that
misnames a parameter, claims more than the check can prove, or filters on a field that does
not exist. Without this a typo loads cleanly and surfaces only as a crash or a wrong verdict.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from plancheck.compliance.rules import Param, Rule
from plancheck.model.types import Opening, Room

ParamKind = Literal["length", "percent"]
Capability = Literal["both", "fail_only", "pass_only"]
Element = Literal["opening", "room", "model"]

_ELEMENT_TYPES: dict[str, type[Opening] | type[Room]] = {"opening": Opening, "room": Room}
VIRTUAL_FILTER_KEYS: dict[str, frozenset[str]] = {"opening": frozenset({"exterior"})}
"""Filter keys the engine computes rather than reads from the element."""

_TOLERANCE_MM = 1e-6


@dataclass(frozen=True)
class CheckSpec:
    """The contract between a check (or scoping function) and the rules that use it."""

    function: Callable[..., Any]
    element: Element
    proves: Capability | None
    """The most the geometry can prove; None for scoping functions, which give no verdict."""
    requirement: Mapping[str, ParamKind] = field(default_factory=dict)
    """Every requirement name the function reads. A rule must give exactly these."""
    checked_exceptions: Mapping[str, Mapping[str, ParamKind]] = field(default_factory=dict)
    """Exceptions the function computes, with the parameters each one reads."""
    connectivity: Literal["none", "openings", "openings_and_rooms"] = "none"
    """Room-graph records the function needs; for scoping functions the engine checks them."""
    uses_check: str | None = None
    """Another check whose rule this one reuses (the route reuses the door width rule)."""
    rule_problems: Callable[[Rule], list[str]] | None = None
    """Extra, check-specific consistency checks on the rule's values."""


def proves_within(declared: Capability | None, capability: Capability | None) -> bool:
    """Whether a rule's ``proves`` claims no more than the check can prove."""
    if capability is None or capability == "both":
        return True
    return declared == capability


def effective_proves(declared: Capability | None, capability: Capability | None) -> Capability:
    """The narrower of what the rule declares and what the check can prove."""
    if capability is not None and capability != "both":
        return capability
    return declared or "both"


def _unit_problem(label: str, param: Param, kind: ParamKind) -> str | None:
    if kind == "percent" and param.unit != "percent":
        return f"{label} must be a percentage, not {param.unit}"
    if kind == "length" and param.unit == "percent":
        return f"{label} must be a length, not a percentage"
    return None


def _names_problems(
    label: str, given: Mapping[str, Param], declared: Mapping[str, ParamKind]
) -> list[str]:
    problems = []
    missing = sorted(set(declared) - set(given))
    extra = sorted(set(given) - set(declared))
    if missing:
        problems.append(f"{label} is missing {missing}")
    if extra:
        problems.append(f"{label} has {extra}, which the check does not read")
    for name, param in given.items():
        if name in declared:
            problem = _unit_problem(f"{label} '{name}'", param, declared[name])
            if problem:
                problems.append(problem)
    return problems


def _literal_values(annotation: Any) -> set[str] | None:
    """The allowed values of a Literal field (also inside ``X | None``), else None."""
    origin = typing.get_origin(annotation)
    if origin is Literal:
        return {str(a) for a in typing.get_args(annotation)}
    if origin in (typing.Union, types.UnionType):
        for arg in typing.get_args(annotation):
            values = _literal_values(arg)
            if values is not None:
                return values
    return None


def filter_problems(element: str, filters: Mapping[str, Any]) -> list[str]:
    """Unknown filter keys, and values outside a fixed set (``kind``, ``operation``)."""
    model = _ELEMENT_TYPES.get(element)
    if model is None:
        return [f"selection on '{element}' cannot have a filter"] if filters else []
    problems = []
    virtual = VIRTUAL_FILTER_KEYS.get(element, frozenset())
    for key, allowed in filters.items():
        if key in virtual:
            continue
        info = model.model_fields.get(key)
        if info is None:
            problems.append(f"filter key '{key}' is not a field of {element}")
            continue
        values = _literal_values(info.annotation)
        if values is None:
            continue
        wanted = allowed if isinstance(allowed, list) else [allowed]
        bad = sorted(str(v) for v in wanted if str(v) not in values)
        if bad:
            problems.append(f"filter '{key}' has {bad}, not among {sorted(values)}")
    return problems


def contract_problems(rule: Rule, specs: Mapping[str, CheckSpec]) -> list[str]:
    """Every way ``rule`` breaks the contract of the function it names. Empty means none."""
    if rule.amends is not None and rule.amends.mode == "delete":
        return []
    spec = specs.get(rule.check or "")
    if spec is None:
        return [f"check '{rule.check}' is not a known {rule.kind} function"]
    problems = []
    if rule.selection is None:
        problems.append("a selection is required")
    else:
        if rule.selection.element != spec.element:
            problems.append(
                f"selection.element is '{rule.selection.element}' but {rule.check} "
                f"tests '{spec.element}'"
            )
        problems += filter_problems(rule.selection.element, rule.selection.filter)
    problems += _names_problems("requirement", rule.requirement, spec.requirement)
    for exception in rule.exceptions:
        if exception.handling != "checked":
            continue
        declared = spec.checked_exceptions.get(exception.id)
        if declared is None:
            problems.append(
                f"exception '{exception.id}' is marked checked, but {rule.check} does not "
                "compute it; mark it surfaced"
            )
            continue
        problems += _names_problems(f"exception '{exception.id}'", exception.params, declared)
    if rule.kind == "technical" and not proves_within(rule.proves, spec.proves):
        problems.append(
            f"proves: {rule.proves} claims more than {rule.check} can prove ({spec.proves})"
        )
    if spec.rule_problems is not None and not problems:
        problems += spec.rule_problems(rule)
    return problems


def turning_space_problems(rule: Rule) -> list[str]:
    """The check places the T that the square and width define; other numbers are another shape.

    So the arm and base clearances must be what that T leaves: width + base = square and
    width + 2 x arm = square.
    """
    req = rule.requirement
    names = ("t_square", "t_width", "t_arm_clear", "t_base_clear")
    if any(req[n].value is None for n in names):
        return []
    square, width, arm, base = (req[n].mm for n in names)
    problems = []
    if abs(width + base - square) > _TOLERANCE_MM:
        problems.append("t_width + t_base_clear must equal t_square")
    if abs(width + 2 * arm - square) > _TOLERANCE_MM:
        problems.append("t_width + 2 x t_arm_clear must equal t_square")
    return problems
