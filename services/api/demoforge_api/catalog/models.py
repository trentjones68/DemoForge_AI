"""Explicit catalog evidence and mapping contracts."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, StringConstraints, field_validator, model_validator

from demoforge_api.analysis.routes import Revision
from demoforge_api.analysis.schema import Statement, StrictModel
from demoforge_api.catalog.matcher import SupportStatus, match_key
from demoforge_api.planning.models import ApprovedRequirement

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ReleaseInput(StrictModel):
    product: ShortText
    version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Release(ReleaseInput):
    model_config = {"extra": "ignore", "strict": False}
    id: UUID
    actor_id: UUID
    created_at: datetime


class CapabilityInput(StrictModel):
    name: ShortText
    description: Statement
    support_status: SupportStatus
    limitations: Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] = ""
    dependencies: Annotated[list[Label], Field(max_length=12)] = Field(default_factory=list)
    match_phrases: Annotated[list[Statement], Field(max_length=12)] = Field(default_factory=list)
    source_title: Label
    source_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1200)]
    source_locator: Label

    @field_validator("source_url")
    @classmethod
    def validate_source(cls, value: str) -> str:
        parsed = HttpUrl(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
            raise ValueError("Use an HTTPS source URL without embedded credentials")
        normalized = str(parsed)
        if len(normalized) > 1200:
            raise ValueError("The source URL is too long")
        return normalized

    @model_validator(mode="after")
    def verify_evidence(self) -> Self:
        if self.support_status in ("partial", "unsupported") and not self.limitations:
            raise ValueError("Explain the support limitation")
        keys = {match_key(phrase) for phrase in self.match_phrases}
        if "" in keys or len(keys) != len(self.match_phrases):
            raise ValueError("Use distinct match phrases with text")
        return self


class Capability(CapabilityInput):
    model_config = {"extra": "ignore", "strict": False}
    id: UUID
    release_id: UUID
    revision: int
    archived: bool
    actor_id: UUID
    created_at: datetime


class CapabilityEdit(CapabilityInput):
    revision: Revision


class MappingEdit(StrictModel):
    revision: Revision
    capability_id: UUID | None
    capability_revision: Revision | None
    rationale: Statement

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if (self.capability_id is None) != (self.capability_revision is None):
            raise ValueError("Select an exact catalog entry and revision")
        return self


class Mapping(BaseModel):
    id: UUID
    revision: int
    session_id: UUID
    requirement_id: UUID
    requirement_revision: int
    requirement_statement: str
    support_status: SupportStatus
    rationale: str
    actor_id: UUID
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    stale_evidence: bool
    capability: Capability | None


class MappingBoard(BaseModel):
    release: Release
    requirements: list[ApprovedRequirement]
    mappings: list[Mapping]
    capabilities: list[Capability]


class CapabilityPage(BaseModel):
    entries: list[Capability]
    more: bool


class Generated(BaseModel):
    added: int
