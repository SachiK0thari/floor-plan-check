"""The rule file format (docs/PROJECT_SPEC.md §9.1).

A rule follows RASE: a Requirement, its Applicability, a Selection of elements, and
Exceptions. Numbers keep the unit they were written in and are converted exactly when
used. Each number can carry the verbatim sentence it was read from.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Unit = Literal["in", "ft", "mm", "m", "percent"]
_MM_PER_UNIT = {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Param(_Base):
    """A value as written in the source, with its unit and supporting quote."""

    value: float | None = Field(allow_inf_nan=False)
    unit: Unit
    quote: str | None = None
    section: str | None = None  # where the quote is, if not the rule's own section

    @property
    def mm(self) -> float:
        """The value in millimetres, converted exactly from the source unit."""
        if self.value is None:
            raise ValueError("param has no value")
        if self.unit == "percent":
            raise ValueError("a percentage is not a length")
        return self.value * _MM_PER_UNIT[self.unit]

    @property
    def fraction(self) -> float:
        if self.value is None or self.unit != "percent":
            raise ValueError("param is not a filled percentage")
        return self.value / 100.0

    def as_written(self) -> str:
        return f"{self.value:g} {self.unit}"


class RuleException(_Base):
    """An exception to the rule. ``checked`` ones are computed; ``surfaced`` ones are shown."""

    id: str
    paraphrase: str
    handling: Literal["checked", "surfaced"]
    params: dict[str, Param] = Field(default_factory=dict)
    quote: str | None = None
    section: str | None = None


class Applicability(_Base):
    """When the rule is in force at all. ``None`` means the rule does not depend on that input."""

    facility_type: list[str] | None = None
    work_type: list[Literal["new", "alteration", "existing"]] | None = None
    occupancy: list[str] | None = None


class Selection(_Base):
    """Which elements the rule tests."""

    element: Literal["opening", "room", "model"]
    filter: dict[str, Any] = Field(default_factory=dict)
    obligated_by: list[str] = Field(default_factory=list)  # scoping rules supplying the set


class Amends(_Base):
    rule: str
    mode: Literal["replace", "delete"]


class Rule(_Base):
    id: str
    kind: Literal["technical", "scoping"]
    code: str
    edition: str
    section: str
    title: str
    paraphrase: str
    check: str | None = None  # name of the check or scoping function; None for deletions
    applicability: Applicability = Field(default_factory=Applicability)
    selection: Selection | None = None
    requirement: dict[str, Param] = Field(default_factory=dict)
    exceptions: list[RuleException] = Field(default_factory=list)
    proves: Literal["both", "fail_only", "pass_only"] | None = None
    quote: str | None = None  # the governing sentence, for rules with no numbers
    source_url: str | None = None
    source_text: str | None = None  # snapshot under rules/sources/, when the text is storable
    jurisdiction: str | None = None
    effective_date: date | None = None
    superseded_date: date | None = None
    amends: Amends | None = None
    verified_by: str | None = None
    status: Literal["draft", "verified"] = "draft"

    @model_validator(mode="after")
    def _check(self) -> Self:
        deletion = self.amends is not None and self.amends.mode == "delete"
        if deletion and (self.check or self.requirement):
            raise ValueError(f"rule {self.id}: a deletion has no check and no params")
        if not deletion and not self.check:
            raise ValueError(f"rule {self.id}: 'check' is required")
        if self.kind == "technical" and not deletion and self.proves is None:
            raise ValueError(f"rule {self.id}: technical rules must declare 'proves'")
        if self.amends is not None and self.jurisdiction is None:
            raise ValueError(f"rule {self.id}: only a jurisdiction's rule can amend another")
        if self.status == "verified":
            if not self.verified_by:
                raise ValueError(f"rule {self.id}: verified rules need 'verified_by'")
            if self.null_params():
                raise ValueError(f"rule {self.id}: verified rules cannot have null params")
        return self

    def all_params(self) -> dict[str, Param]:
        """Every param in the rule, including those inside exceptions, by dotted name."""
        params = dict(self.requirement)
        for exception in self.exceptions:
            for name, param in exception.params.items():
                params[f"{exception.id}.{name}"] = param
        return params

    def null_params(self) -> list[str]:
        return [name for name, param in self.all_params().items() if param.value is None]

    @property
    def runnable(self) -> bool:
        """A rule with any unfilled number never runs."""
        return not self.null_params()

    def exception(self, exception_id: str) -> RuleException:
        return next(e for e in self.exceptions if e.id == exception_id)
