from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from plancheck.compliance.registry import (
    RULES_DIR,
    LoadedRule,
    RuleError,
    load_ruleset,
    quote_problems,
    resolve,
)
from plancheck.compliance.rules import Param, Rule

# ---------------------------------------------------------------- the shipped ADA rules


@pytest.fixture(scope="module")
def ada() -> dict[str, LoadedRule]:
    return {loaded.rule.id: loaded for loaded in load_ruleset("ada_2010")}


def test_ada_rules_are_complete_and_every_quote_matches(ada: dict[str, LoadedRule]) -> None:
    assert len(ada) == 7
    for loaded in ada.values():
        assert loaded.rule.status == "verified"
        assert loaded.rule.runnable
        assert quote_problems(loaded) == [], loaded.rule.id


def test_ada_values_are_pinned(ada: dict[str, LoadedRule]) -> None:
    # A second, independent record of the values: an edit to a rule file has to be made
    # here too, on purpose.
    def values(rule_id: str) -> dict[str, tuple[float | None, str]]:
        params = ada[rule_id].rule.all_params()
        return {name: (param.value, param.unit) for name, param in params.items()}

    assert values("ada2010.door-clear-width") == {
        "min_clear_width": (32, "in"),
        "deep-opening.depth": (24, "in"),
        "deep-opening.min_clear_width": (36, "in"),
    }
    assert values("ada2010.door-maneuvering-clearance") == {
        "pull_perpendicular": (60, "in"),
        "pull_beyond_latch": (18, "in"),
        "push_perpendicular": (48, "in"),
        "push_beyond_latch": (0, "in"),
        "closer-and-latch.push_beyond_latch_added": (12, "in"),
    }
    assert values("ada2010.toilet-room-turning-space") == {
        "circle_diameter": (60, "in"),
        "t_square": (60, "in"),
        "t_width": (36, "in"),
        "t_arm_clear": (12, "in"),
        "t_base_clear": (24, "in"),
    }
    assert values("ada2010.walking-surface-clear-width") == {
        "min_clear_width": (36, "in"),
        "short-reduction.reduced_width": (32, "in"),
        "short-reduction.max_length": (24, "in"),
        "short-reduction.separation_length": (48, "in"),
        "short-reduction.separation_width": (36, "in"),
    }
    assert values("ada2010.scoping.entrances") == {"min_share": (60, "percent")}


def test_values_convert_exactly_not_to_the_printed_metric(ada: dict[str, LoadedRule]) -> None:
    # The Standards print "32 inches (815 mm)". 815 is a rounded figure; 32 in is 812.8 mm.
    width = ada["ada2010.door-clear-width"].rule.requirement["min_clear_width"]
    assert width.mm == pytest.approx(812.8)
    assert width.as_written() == "32 in"
    assert ada["ada2010.scoping.entrances"].rule.requirement["min_share"].fraction == 0.6


def test_ada_rules_cannot_be_amended_and_are_not_local(ada: dict[str, LoadedRule]) -> None:
    assert all(loaded.rule.jurisdiction is None for loaded in ada.values())
    assert all(loaded.rule.amends is None for loaded in ada.values())


# ---------------------------------------------------------------- the quote check itself


def edited(loaded: LoadedRule, tmp_path: Path, change: Any) -> LoadedRule:
    """A copy of a shipped rule with one edit applied to its YAML data."""
    data = yaml.safe_load(loaded.path.read_text())
    change(data)
    return LoadedRule(Rule.model_validate(data), loaded.ruleset, tmp_path / "x.yaml", "0")


def test_wrong_number_is_caught(ada: dict[str, LoadedRule], tmp_path: Path) -> None:
    def change(data: dict[str, Any]) -> None:
        data["requirement"]["min_clear_width"]["value"] = 34

    problems = quote_problems(edited(ada["ada2010.door-clear-width"], tmp_path, change))
    assert problems == ["min_clear_width: quote does not contain '34 in'"]


def test_number_must_match_whole(ada: dict[str, LoadedRule], tmp_path: Path) -> None:
    # "2 in" must not be accepted because the quote says "32 inches".
    def change(data: dict[str, Any]) -> None:
        data["requirement"]["min_clear_width"]["value"] = 2

    problems = quote_problems(edited(ada["ada2010.door-clear-width"], tmp_path, change))
    assert problems == ["min_clear_width: quote does not contain '2 in'"]


def test_altered_quote_is_caught(ada: dict[str, LoadedRule], tmp_path: Path) -> None:
    def change(data: dict[str, Any]) -> None:
        data["requirement"]["min_clear_width"]["quote"] = (
            "Door openings shall provide a clear width of 32 inches (815 mm) maximum."
        )

    problems = quote_problems(edited(ada["ada2010.door-clear-width"], tmp_path, change))
    assert problems == [
        "min_clear_width: quote not found under section 404.2.3 (it is nowhere in the source)"
    ]


def test_quote_from_the_wrong_section_is_caught(ada: dict[str, LoadedRule], tmp_path: Path) -> None:
    # The 60 inch circle is real text, but it is in 304.3.1, not after 603.2.1.
    def change(data: dict[str, Any]) -> None:
        del data["requirement"]["circle_diameter"]["section"]

    problems = quote_problems(edited(ada["ada2010.toilet-room-turning-space"], tmp_path, change))
    assert problems == [
        "circle_diameter: quote not found under section 603.2.1 (it is elsewhere in the source)"
    ]


def test_verified_value_needs_a_quote(ada: dict[str, LoadedRule], tmp_path: Path) -> None:
    def change(data: dict[str, Any]) -> None:
        del data["requirement"]["min_clear_width"]["quote"]

    problems = quote_problems(edited(ada["ada2010.door-clear-width"], tmp_path, change))
    assert problems == ["min_clear_width: verified value has no quote"]


# ---------------------------------------------------------------- rule validation


def rule_data(**overrides: Any) -> dict[str, Any]:
    """A made-up rule for a made-up code. The numbers mean nothing."""
    data: dict[str, Any] = {
        "id": "testcode.corridor-min-width",
        "kind": "technical",
        "code": "Test Code",
        "edition": "1",
        "section": "1.1",
        "title": "Corridor width",
        "paraphrase": "Corridors have a minimum width.",
        "check": "corridor_min_width",
        "selection": {"element": "room", "filter": {"room_type": ["corridor"]}},
        "requirement": {"min_width": {"value": 1000, "unit": "mm"}},
        "proves": "both",
    }
    return data | overrides


def test_param_refuses_to_convert_a_missing_value() -> None:
    with pytest.raises(ValueError, match="no value"):
        _ = Param(value=None, unit="in").mm


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "verified"}, "need 'verified_by'"),
        (
            {
                "status": "verified",
                "verified_by": "x",
                "requirement": {"min_width": {"value": None, "unit": "mm"}},
            },
            "cannot have null params",
        ),
        ({"proves": None}, "must declare 'proves'"),
        ({"check": None}, "'check' is required"),
        ({"amends": {"rule": "a", "mode": "replace"}}, "only a jurisdiction's rule"),
        (
            {"jurisdiction": "x", "amends": {"rule": "a", "mode": "delete"}},
            "a deletion has no check",
        ),
        ({"surprise": 1}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_rules_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Rule.model_validate(rule_data(**overrides))


# ---------------------------------------------------------------- layering


def write_rules(root: Path, ruleset: str, *rules: dict[str, Any]) -> None:
    folder = root / ruleset
    folder.mkdir(parents=True, exist_ok=True)
    for data in rules:
        (folder / f"{data['id']}.yaml").write_text(yaml.safe_dump(data))


def local(
    slug: str, rule_id: str, amends: str, mode: str = "replace", width: int = 1200
) -> dict[str, Any]:
    data = rule_data(id=rule_id, jurisdiction=slug, amends={"rule": amends, "mode": mode})
    if mode == "delete":
        data.update(check=None, requirement={}, proves=None)
    else:
        data["requirement"] = {"min_width": {"value": width, "unit": "mm"}}
    return data


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    write_rules(tmp_path, "ibc_style", rule_data(), rule_data(id="testcode.room-min-area"))
    return tmp_path


def ids(rules_dir: Path, *rulesets: str) -> list[str]:
    return [loaded.rule.id for loaded in resolve(rulesets, rules_dir).rules]


def test_replace_drops_the_base_rule_and_is_reported(rules_dir: Path) -> None:
    write_rules(rules_dir, "local/st", local("st", "st.corridor", "testcode.corridor-min-width"))
    resolved = resolve(["ibc_style", "local/st"], rules_dir)
    assert [r.rule.id for r in resolved.rules] == ["testcode.room-min-area", "st.corridor"]
    assert resolved.get("st.corridor").rule.requirement["min_width"].value == 1200
    assert resolved.notes == ["st.corridor replaces testcode.corridor-min-width (Test Code)"]


def test_delete_removes_the_base_rule_and_is_reported(rules_dir: Path) -> None:
    write_rules(
        rules_dir,
        "local/st",
        local("st", "st.no-corridor", "testcode.corridor-min-width", "delete"),
    )
    resolved = resolve(["ibc_style", "local/st"], rules_dir)
    assert [r.rule.id for r in resolved.rules] == ["testcode.room-min-area"]
    assert resolved.notes == ["st.no-corridor deletes testcode.corridor-min-width (Test Code)"]


def test_chain_of_two_amendments_resolves_in_order(rules_dir: Path) -> None:
    # Model code, then the state's amendment, then the city's amendment of the state's.
    write_rules(rules_dir, "local/st", local("st", "st.corridor", "testcode.corridor-min-width"))
    write_rules(rules_dir, "local/city", local("city", "city.corridor", "st.corridor", width=1500))
    resolved = resolve(["ibc_style", "local/st", "local/city"], rules_dir)
    assert [r.rule.id for r in resolved.rules] == ["testcode.room-min-area", "city.corridor"]
    assert resolved.get("city.corridor").rule.requirement["min_width"].value == 1500
    assert len(resolved.notes) == 2


def test_without_the_local_ruleset_the_base_rule_stands(rules_dir: Path) -> None:
    write_rules(rules_dir, "local/st", local("st", "st.corridor", "testcode.corridor-min-width"))
    assert ids(rules_dir, "ibc_style") == ["testcode.corridor-min-width", "testcode.room-min-area"]


def test_ada_rules_cannot_be_amended(rules_dir: Path) -> None:
    shutil.copytree(RULES_DIR / "ada_2010", rules_dir / "ada_2010")
    write_rules(rules_dir, "local/st", local("st", "st.doors", "ada2010.door-clear-width"))
    with pytest.raises(RuleError, match="ada_2010 rules cannot be amended"):
        resolve(["ada_2010", "local/st"], rules_dir)


def test_two_rules_cannot_amend_the_same_target(rules_dir: Path) -> None:
    write_rules(
        rules_dir,
        "local/st",
        local("st", "st.a", "testcode.corridor-min-width"),
        local("st", "st.b", "testcode.corridor-min-width"),
    )
    with pytest.raises(RuleError, match=r"st\.b and st\.a both amend"):
        resolve(["ibc_style", "local/st"], rules_dir)


def test_amendment_must_target_an_earlier_ruleset(rules_dir: Path) -> None:
    # Amending a rule in the same ruleset (or a later one) is how a cycle would start.
    write_rules(
        rules_dir,
        "local/st",
        local("st", "st.a", "testcode.corridor-min-width"),
        local("st", "st.b", "st.a"),
    )
    with pytest.raises(RuleError, match="not in an earlier ruleset"):
        resolve(["ibc_style", "local/st"], rules_dir)
    with pytest.raises(RuleError, match="not in an earlier ruleset"):
        resolve(["local/st", "ibc_style"], rules_dir)


def test_duplicate_ids_are_rejected(rules_dir: Path) -> None:
    clash = rule_data(jurisdiction="st")
    write_rules(rules_dir, "local/st", clash)
    with pytest.raises(RuleError, match="defined more than once"):
        resolve(["ibc_style", "local/st"], rules_dir)


def test_local_rule_must_carry_its_ruleset_slug(rules_dir: Path) -> None:
    write_rules(rules_dir, "local/st", local("other", "st.corridor", "testcode.corridor-min-width"))
    with pytest.raises(RuleError, match="jurisdiction is 'other'"):
        load_ruleset("local/st", rules_dir)


def test_rules_with_unfilled_values_do_not_run(rules_dir: Path) -> None:
    draft = rule_data(id="testcode.draft", requirement={"min_width": {"value": None, "unit": "mm"}})
    write_rules(rules_dir, "ibc_style", draft)
    resolved = resolve(["ibc_style"], rules_dir)
    assert resolved.not_runnable == [("testcode.draft", "values not filled in: ['min_width']")]
    assert "testcode.draft" not in [r.rule.id for r in resolved.runnable]
    assert "testcode.draft" in [r.rule.id for r in resolved.rules]  # still listed


def test_fingerprint_changes_when_a_rule_file_changes(rules_dir: Path) -> None:
    before = resolve(["ibc_style"], rules_dir).fingerprint()
    write_rules(rules_dir, "ibc_style", rule_data(title="Corridor width (edited)"))
    after = resolve(["ibc_style"], rules_dir).fingerprint()
    assert [rule_id for rule_id, _ in before] == [rule_id for rule_id, _ in after]
    assert before != after
