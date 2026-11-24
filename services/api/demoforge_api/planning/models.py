"""Public discovery planning contracts."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from demoforge_api.analysis.routes import Citation, Revision
from demoforge_api.analysis.schema import Statement, StrictModel
from demoforge_api.planning.normalizer import Category, GapStatus, Kind, Priority

MAX_ITEMS = 100
MAX_LINKS = 16


class Fields(StrictModel):
    statement: Statement
    rationale: Statement
    category: Category
    priority: Priority
    owner_id: UUID | None = None
    status: GapStatus | None = None
    affected_requirement_ids: Annotated[list[UUID], Field(max_length=MAX_LINKS)] = Field(
        default_factory=list
    )


class CreateItem(Fields):
    kind: Kind


class EditItem(Fields):
    revision: Revision


class PlanRevision(BaseModel):
    revision: int
    statement: str
    rationale: str
    category: Category
    priority: Priority
    owner_id: UUID | None
    status: GapStatus | None
    actor_id: UUID
    created_at: datetime
    approved_at: datetime | None
    approved_by: UUID | None
    affected_requirement_ids: list[UUID]


class PlanItem(PlanRevision):
    id: UUID
    kind: Kind
    generated: bool
    stale_source: bool
    source_revision: int | None
    evidence: list[Citation]


class Plan(BaseModel):
    items: list[PlanItem]
    owners: list[UUID]
    has_approved_insights: bool


class Normalized(BaseModel):
    added: int


class ApprovedRequirement(BaseModel):
    """The only leads available for downstream storyboard planning."""

    id: UUID
    session_id: UUID
    revision: int
    statement: str
    rationale: str
    category: Category
    priority: Priority
    approved_at: datetime
    approved_by: UUID
    source_job_id: UUID | None
    source_finding_id: UUID | None
    source_revision: int | None
