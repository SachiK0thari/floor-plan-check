"""What a check returns, and what a scoping rule returns."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from plancheck.compliance.verdict import Verdict
from plancheck.model.types import Measured, Point


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Base):
    """Geometry to draw on the plan with a result."""

    kind: Literal["polygon", "line", "point"]
    points: list[Point]
    label: str | None = None


class Obligation(_Base):
    """A scoping rule's output: a group of elements of which some number must comply."""

    scoping_rule_id: str
    group_id: str
    element_ids: list[str]
    min_count: int
    reason: str


class MeasurementSemantics(_Base):
    """An explicit scalar comparison contract emitted by a check implementation."""

    quantity: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    relation: Literal["min", "max"]
    unresolved_conditions: list[str] = Field(default_factory=list)


class RuleCitation(_Base):
    code: str
    edition: str
    section: str
    source_url: str | None = None
    jurisdiction: str | None = None
    ruleset: str
    effective_date: date | None = None
    superseded_date: date | None = None


class Finding(_Base):
    """The outcome of one check on one element (or group of elements)."""

    rule_id: str
    code: str
    section: str
    title: str
    verdict: Verdict
    element_ids: list[str]
    measured: Measured | None = None
    required: str | None = None  # as written in the source, e.g. "32 in"
    required_mm: float | None = None
    reason: str | None = None  # why unknown, not applicable, or what was assumed
    obligations: list[str] = Field(default_factory=list)  # why the element was tested
    surfaced_exceptions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    group: str | None = None  # set on a group result (e.g. "room:R1")
    regime: Literal["ada", "building_code"] | None = None
    citation: RuleCitation | None = None
    semantics: MeasurementSemantics | None = None
    provisional: bool = False


class GoverningRequirement(_Base):
    """A derived scalar requirement; source findings remain the authoritative results."""

    element_id: str
    quantity: str
    basis: str
    relation: Literal["min", "max"]
    required_mm: float
    required: str
    governing_rule_ids: list[str]
    source_findings: list[Finding]
    reason: str


class ComparisonOmission(_Base):
    element_id: str
    quantity: str
    rule_ids: list[str]
    reason: str


class CheckOutcome(_Base):
    """What a check function returns; the engine turns it into a Finding."""

    verdict: Verdict
    measured: Measured | None = None
    required: str | None = None
    required_mm: float | None = None
    reason: str | None = None
    surfaced_exceptions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    semantics: MeasurementSemantics | None = None
