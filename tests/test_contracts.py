"""Check contracts: a rule file must match what its check reads and can prove (A1, A6)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from plancheck.compliance.checks import CHECKS
from plancheck.compliance.context import CheckContext
from plancheck.compliance.contracts import effective_proves, proves_within
from plancheck.compliance.engine import run
from plancheck.compliance.registry import (
    RULES_DIR,
    ResolvedRules,
    RuleError,
    contract_warnings,
    load_ruleset,
    resolve,
)
from plancheck.compliance.rules import Rule
from plancheck.compliance.scoping.doors import SCOPING
from plancheck.compliance.verdict import Verdict
from plancheck.model.types import BuildingModel, Measured, ProjectContext

ADA = RULES_DIR / "ada_2010"


def ada_rule(filename: str) -> dict[str, Any]:
    data = yaml.safe_load((ADA / filename).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def load_one(tmp_path: Path, data: dict[str, Any]) -> None:
    folder = tmp_path / "trial"
    folder.mkdir()
    (folder / "rule.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    load_ruleset("trial", tmp_path)


def edited(filename: str, edit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    data = ada_rule(filename)
    edit(data)
    return data


def test_shipped_rulesets_meet_their_contracts() -> None:
    assert len(load_ruleset("ada_2010")) == 7
    assert len(load_ruleset("local/maharashtra")) == 1
    resolve(["ada_2010", "local/maharashtra"])


def set_key(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        node = data
        for p in parents:
            node = node[p]
        node[last] = value

    return edit


def rename_requirement(old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        data["requirement"][new] = data["requirement"].pop(old)

    return edit


def drop_requirement(name: str) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        del data["requirement"][name]

    return edit


def add_exception(exception: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        data["exceptions"].append(exception)

    return edit


def rename_exception_param(
    exception_id: str, old: str, new: str
) -> Callable[[dict[str, Any]], None]:
    def edit(data: dict[str, Any]) -> None:
        exc = next(e for e in data["exceptions"] if e["id"] == exception_id)
        exc["params"][new] = exc["params"].pop(old)

    return edit


@pytest.mark.parametrize(
    ("filename", "edit", "message"),
    [
        # The design note's "Observed" table (A6).
        (
            "door_clear_width.yaml",
            rename_requirement("min_clear_width", "min_width"),
            "requirement is missing ['min_clear_width']",
        ),
        (
            "toilet_room_turning_space.yaml",
            set_key("selection.filter", {"room_typ": ["bathroom"]}),
            "filter key 'room_typ' is not a field of room",
        ),
        (
            "toilet_room_turning_space.yaml",
            set_key("check", "turning_spce"),
            "check 'turning_spce' is not a known technical function",
        ),
        # 1. a scoping rule may only name a scoping function
        (
            "scoping_entrances.yaml",
            set_key("check", "opening_clear_width"),
            "is not a known scoping function",
        ),
        # 2. the selected element must be the one the check tests
        (
            "door_clear_width.yaml",
            set_key("selection", {"element": "room"}),
            "selection.element is 'room' but opening_clear_width tests 'opening'",
        ),
        # 3. exact names, and the declared kind of unit
        (
            "toilet_room_turning_space.yaml",
            drop_requirement("t_arm_clear"),
            "requirement is missing ['t_arm_clear']",
        ),
        (
            "door_clear_width.yaml",
            set_key("requirement.min_clear_width", {"value": 32, "unit": "percent"}),
            "'min_clear_width' must be a length, not a percentage",
        ),
        (
            "scoping_entrances.yaml",
            set_key("requirement.min_share", {"value": 60, "unit": "in"}),
            "'min_share' must be a percentage, not in",
        ),
        # 4. checked exceptions must be computed by the check, with its parameter names
        (
            "door_clear_width.yaml",
            add_exception({"id": "made-up", "paraphrase": "x", "handling": "checked"}),
            "exception 'made-up' is marked checked",
        ),
        (
            "door_clear_width.yaml",
            rename_exception_param("deep-opening", "depth", "deep"),
            "exception 'deep-opening' is missing ['depth']",
        ),
        # 5. filter values outside a fixed set
        (
            "door_clear_width.yaml",
            set_key("selection.filter", {"kind": ["dor"]}),
            "filter 'kind' has ['dor']",
        ),
        (
            "door_maneuvering_clearance.yaml",
            set_key("selection.filter", {"kind": ["door"], "operation": ["swinging"]}),
            "filter 'operation' has ['swinging']",
        ),
        # 6. proves may not exceed the check's capability (A1)
        (
            "accessible_route.yaml",
            set_key("proves", "both"),
            "proves: both claims more than accessible_route_exists can prove (fail_only)",
        ),
        (
            "toilet_room_turning_space.yaml",
            set_key("proves", "both"),
            "claims more than turning_space can prove",
        ),
        (
            "door_maneuvering_clearance.yaml",
            set_key("proves", "pass_only"),
            "claims more than door_maneuvering_clearance can prove",
        ),
        # 7. the T's clearances must be what its square and width leave
        (
            "toilet_room_turning_space.yaml",
            set_key("requirement.t_arm_clear.value", 14),
            "t_width + 2 x t_arm_clear must equal t_square",
        ),
        (
            "toilet_room_turning_space.yaml",
            set_key("requirement.t_base_clear.value", 20),
            "t_width + t_base_clear must equal t_square",
        ),
    ],
)
def test_contract_violations_are_rejected_at_load(
    tmp_path: Path, filename: str, edit: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(RuleError, match="rule ") as caught:
        load_one(tmp_path, edited(filename, edit))
    assert message in str(caught.value)


def test_legal_variations_load(tmp_path: Path) -> None:
    # A both-capable check may be narrowed, and a surfaced exception may carry any params.
    narrowed = edited("door_clear_width.yaml", set_key("proves", "fail_only"))
    narrowed["exceptions"].append(
        {
            "id": "anything",
            "paraphrase": "x",
            "handling": "surfaced",
            "params": {"whatever": {"value": 1, "unit": "in"}},
        }
    )
    load_one(tmp_path, narrowed)


def test_obligated_by_must_name_a_resolved_scoping_rule(tmp_path: Path) -> None:
    folder = tmp_path / "trial"
    folder.mkdir()
    rule = ada_rule("door_clear_width.yaml")  # obligated by the two ADA scoping rules
    (folder / "rule.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    load_ruleset("trial", tmp_path)  # each file is valid on its own
    with pytest.raises(RuleError, match="is obligated by"):
        resolve(["trial"], tmp_path)


def test_room_type_values_outside_the_map_are_warnings() -> None:
    rule = load_ruleset("ada_2010")[0].rule
    assert contract_warnings(rule) == []
    data = edited(
        "toilet_room_turning_space.yaml", set_key("selection.filter", {"room_type": ["loo"]})
    )
    assert contract_warnings(Rule.model_validate(data)) == [
        "room_type ['loo'] is not a value in configs/room_type_map.yaml"
    ]


def test_every_declared_contract_is_coherent() -> None:
    for name, spec in {**CHECKS, **SCOPING}.items():
        if spec.uses_check is not None:
            assert spec.uses_check in CHECKS, name
    assert all(spec.proves is not None for spec in CHECKS.values())
    assert all(spec.proves is None for spec in SCOPING.values())


@pytest.mark.parametrize(
    ("declared", "capability", "within", "effective"),
    [
        ("both", "both", True, "both"),
        ("fail_only", "both", True, "fail_only"),
        ("both", "fail_only", False, "fail_only"),
        ("fail_only", "fail_only", True, "fail_only"),
        ("pass_only", "fail_only", False, "fail_only"),
        (None, None, True, "both"),
    ],
)
def test_proves_rules(declared: Any, capability: Any, within: bool, effective: str) -> None:
    assert proves_within(declared, capability) is within
    assert effective_proves(declared, capability) == effective


def test_engine_bounds_verdicts_even_when_the_registry_is_bypassed(
    two_rooms: BuildingModel,
) -> None:
    """A hand-built rule list claiming ``proves: both`` on fail-only checks still gets unknown."""
    resolved = resolve(["ada_2010"])
    widened = [
        dataclasses.replace(r, rule=r.rule.model_copy(update={"proves": "both"}))
        if r.rule.check in ("accessible_route_exists", "door_maneuvering_clearance")
        else r
        for r in resolved.rules
    ]
    bypassed = ResolvedRules(rulesets=resolved.rulesets, rules=widened)
    project = ProjectContext(
        facility_type="commercial_facility", work_type="new", permit_date=date(2026, 1, 1)
    )
    model = two_rooms.model_copy(update={"project": project})
    ctx = CheckContext(
        k=2.0, clear_width_deductions={"swing": Measured(value_mm=50, sigma_mm=0, source="user")}
    )
    report = run(model, bypassed, ctx)
    for rule_id in ("ada2010.accessible-route", "ada2010.door-maneuvering-clearance"):
        verdicts = {f.verdict for f in report.for_rule(rule_id)} - {Verdict.NOT_APPLICABLE}
        assert verdicts == {Verdict.UNKNOWN}, rule_id
        assert all(
            (f.reason or "").startswith("check can only prove fail only")
            for f in report.for_rule(rule_id)
            if f.verdict is Verdict.UNKNOWN
        )
