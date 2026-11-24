"""What a check returns, and what a scoping rule returns."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from plancheck.compliance.verdict import Verdict, margin_in_sigmas
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
    unresolved_reason: str | None = None
    """Set when the group itself cannot be identified; the roll-up is then unknown."""


class MeasurementSemantics(_Base):
    """An explicit scalar comparison contract emitted by a check implementation."""

    quantity: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    relation: Literal["min", "max"]
    unresolved_conditions: list[str] = Field(default_factory=list)


class NamedMeasurement(_Base):
    """One of the measurements a check makes, with its own requirement and verdict (C6).

    Compound checks (door maneuvering, corridor runs) make several; the review queue needs
    each one's margin, which a single ``measured`` value cannot carry.
    """

    name: str
    measured: Measured
    required: str  # as written in the source
    required_mm: float
    relation: Literal["min", "max"]
    verdict: Verdict

    @property
    def margin_sigmas(self) -> float:
        return margin_in_sigmas(self.measured, self.required_mm, self.relation)


def tightest(measurements: list[NamedMeasurement]) -> NamedMeasurement | None:
    """The measurement closest to failing: smallest margin in sigmas, then in millimetres."""

    def key(m: NamedMeasurement) -> tuple[float, float]:
        mm = m.measured.value_mm - m.required_mm
        return (m.margin_sigmas, mm if m.relation == "min" else -mm)

    return min(measurements, key=key) if measurements else None


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
    measurements: list[NamedMeasurement] = Field(default_factory=list)
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
    measurements: list[NamedMeasurement] = Field(default_factory=list)
    reason: str | None = None
    surfaced_exceptions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    semantics: MeasurementSemantics | None = None
