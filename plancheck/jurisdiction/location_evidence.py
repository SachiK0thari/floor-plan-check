"""Unconfirmed location hints and their drawing-text provenance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LocationField = Literal[
    "address", "country", "state", "city", "planning_authority", "jurisdiction_hint"
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextEvidence(_Base):
    source: str
    method: Literal["pdf_text", "dxf_text"]
    raw_text: str
    page: int | None = Field(default=None, ge=1)
    layout: str | None = None
    entity_handle: str | None = None
    field_label: str | None = None
    anchor: tuple[float, float] | None = None
    coordinate_space: Literal["pdf_user_space", "dxf_millimetres", "dxf_drawing_units"]
    page_rotation_degrees: int = 0
    pdf_user_unit: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    page_crop_box: tuple[float, float, float, float] | None = None
    position_kind: Literal["text_fragment_anchor"] = "text_fragment_anchor"


class LocationCandidate(_Base):
    field: LocationField
    value: str
    evidence: list[TextEvidence]


class LocationExtraction(_Base):
    schema_version: Literal[1] = 1
    source: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["missing", "needs_confirmation", "ambiguous"]
    candidates: list[LocationCandidate] = Field(default_factory=list)
    conflicting_fields: list[LocationField] = Field(default_factory=list)
    pages_without_text: list[int] = Field(default_factory=list)
    unresolved_labels: list[str] = Field(default_factory=list)
    requires_confirmation: Literal[True] = True
    notes: list[str] = Field(default_factory=list)
