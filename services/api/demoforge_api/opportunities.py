from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import Connection, Engine, text

from demoforge_api.auth import TokenVerifier
from demoforge_api.request_access import access_dependencies
from demoforge_api.workspaces import Role, find_workspace


class Stage(StrEnum):
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    DEMO_PLANNING = "demo_planning"
    DEMO_SCHEDULED = "demo_scheduled"
    FOLLOW_UP = "follow_up"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Version = Annotated[int, Field(strict=True, ge=1, le=2147483647)]
ArchiveFilter = Literal["active", "archived", "all"]
Order = Literal["recent", "demo_date", "name"]
ORDER_BY: dict[Order, str] = {
    "recent": "updated_at DESC, id",
    "demo_date": "demo_date ASC NULLS LAST, id",
    "name": "lower(name), id",
}
ARCHIVE_WHERE: dict[ArchiveFilter, str] = {
    "active": "archived_at IS NULL",
    "archived": "archived_at IS NOT NULL",
    "all": "true",
}


class OpportunityWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    company: Name
    stage: Stage
    product: Name
    demo_date: date | None = None
    use_case: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""
    owner_id: UUID | None = None

    @field_validator("demo_date", mode="before")
    @classmethod
    def validate_demo_date(cls, value: object) -> date | None:
        if value is None:
            return None
        if type(value) is date:
            return value
        if isinstance(value, str) and len(value) == 10:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        raise ValueError("Use a target demo date in YYYY-MM-DD format")


class OpportunityUpdate(OpportunityWrite):
    version: Version


class ArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Version


class OpportunitySummary(BaseModel):
    id: UUID
    workspace_id: UUID
    owner_id: UUID | None
    name: str
    company: str
    stage: Stage
    product: str
    demo_date: date | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class Opportunity(OpportunitySummary):
    use_case: str
    notes: str


class OpportunityPage(BaseModel):
    items: list[OpportunitySummary]
    page: int
    has_next: bool


def get_record(connection: Connection, workspace_id: UUID, opportunity_id: UUID) -> Opportunity:
    row = (
        connection.execute(
            text(
                "SELECT * FROM demoforge.opportunities WHERE workspace_id = :workspace AND id = :id"
            ),
            {"workspace": workspace_id, "id": opportunity_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Opportunity not found")
    return Opportunity.model_validate(row)


def require_writer(role: Role, actor: UUID, owner: UUID | None) -> None:
    if role != Role.ADMIN and (role != Role.SALES_ENGINEER or owner != actor):
        raise HTTPException(
            403, "Only the assigned owner or a workspace admin may make this change"
        )


def eligible_owner(connection: Connection, workspace_id: UUID, owner_id: UUID) -> None:
    allowed = connection.execute(
        text("SELECT demoforge.opportunity_owner_eligible(:workspace, :owner)"),
        {"workspace": workspace_id, "owner": owner_id},
    ).scalar_one()
    if allowed is not True:
        raise HTTPException(422, "Choose an admin or sales engineer in this workspace")


def opportunity_router(engine: Engine | None, verifier: TokenVerifier) -> APIRouter:
    router = APIRouter(prefix="/v1/workspaces/{workspace_id}/opportunities", tags=["opportunities"])
    authenticate, transaction = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(transaction, scope="function")]

    @router.get("")
    def list_opportunities(
        workspace_id: UUID,
        connection: Database,
        actor: Actor,
        page: Annotated[int, Query(ge=1, le=10000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        sort: Order = "recent",
        archive: ArchiveFilter = "active",
        stage: Stage | None = None,
    ) -> OpportunityPage:
        find_workspace(connection, workspace_id, actor)
        rows = (
            connection.execute(
                text(f"""
                SELECT id, workspace_id, owner_id, name, company, stage, product,
                       demo_date, archived_at, created_at, updated_at, version
                FROM demoforge.opportunities
                WHERE workspace_id = :workspace AND {ARCHIVE_WHERE[archive]}
                    AND (CAST(:stage AS text) IS NULL OR stage = :stage)
                ORDER BY {ORDER_BY[sort]} LIMIT :limit OFFSET :offset
            """),
                {
                    "workspace": workspace_id,
                    "stage": stage,
                    "limit": page_size + 1,
                    "offset": (page - 1) * page_size,
                },
            )
            .mappings()
            .all()
        )
        return OpportunityPage(
            items=[OpportunitySummary.model_validate(row) for row in rows[:page_size]],
            page=page,
            has_next=len(rows) > page_size and page < 10000,
        )

    @router.get("/{opportunity_id}")
    def detail(
        workspace_id: UUID, opportunity_id: UUID, connection: Database, actor: Actor
    ) -> Opportunity:
        find_workspace(connection, workspace_id, actor)
        return get_record(connection, workspace_id, opportunity_id)

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create(
        workspace_id: UUID, body: OpportunityWrite, connection: Database, actor: Actor
    ) -> Opportunity:
        workspace = find_workspace(connection, workspace_id, actor)
        owner = body.owner_id or actor
        require_writer(workspace.role, actor, owner)
        eligible_owner(connection, workspace_id, owner)
        row = (
            connection.execute(
                text("""
                INSERT INTO demoforge.opportunities
                    (workspace_id, owner_id, name, company, stage, product,
                     demo_date, use_case, notes)
                VALUES (:workspace_id, :owner_id, :name, :company, :stage, :product,
                        :demo_date, :use_case, :notes)
                RETURNING *
            """),
                body.model_dump() | {"workspace_id": workspace_id, "owner_id": owner},
            )
            .mappings()
            .one()
        )
        return Opportunity.model_validate(row)

    def editable(
        connection: Connection,
        workspace_id: UUID,
        opportunity_id: UUID,
        actor: UUID,
        version: int,
    ) -> tuple[Role, Opportunity]:
        role = find_workspace(connection, workspace_id, actor).role
        opportunity = get_record(connection, workspace_id, opportunity_id)
        require_writer(role, actor, opportunity.owner_id)
        if opportunity.archived_at is not None:
            raise HTTPException(409, "Archived opportunities are read only")
        if version != opportunity.version:
            raise HTTPException(409, "This opportunity changed. Reload it and try again.")
        return role, opportunity

    @router.put("/{opportunity_id}")
    def update(
        workspace_id: UUID,
        opportunity_id: UUID,
        body: OpportunityUpdate,
        connection: Database,
        actor: Actor,
    ) -> Opportunity:
        role, existing = editable(connection, workspace_id, opportunity_id, actor, body.version)
        owner = body.owner_id or existing.owner_id
        require_writer(role, actor, owner)
        if owner is not None and owner != existing.owner_id:
            eligible_owner(connection, workspace_id, owner)
        row = (
            connection.execute(
                text("""
                UPDATE demoforge.opportunities
                SET owner_id = :owner_id, name = :name, company = :company, stage = :stage,
                    product = :product, demo_date = :demo_date, use_case = :use_case, notes = :notes
                WHERE workspace_id = :workspace_id AND id = :id AND version = :version
                    AND archived_at IS NULL
                RETURNING *
            """),
                body.model_dump()
                | {"workspace_id": workspace_id, "id": opportunity_id, "owner_id": owner},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(409, "This opportunity changed. Reload it and try again.")
        return Opportunity.model_validate(row)

    @router.post("/{opportunity_id}/archive")
    def archive_opportunity(
        workspace_id: UUID,
        opportunity_id: UUID,
        body: ArchiveRequest,
        connection: Database,
        actor: Actor,
    ) -> Opportunity:
        editable(connection, workspace_id, opportunity_id, actor, body.version)
        row = (
            connection.execute(
                text("""
                UPDATE demoforge.opportunities SET archived_at = statement_timestamp()
                WHERE workspace_id = :workspace AND id = :id AND version = :version
                    AND archived_at IS NULL
                RETURNING *
            """),
                {"workspace": workspace_id, "id": opportunity_id, "version": body.version},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(409, "This opportunity changed. Reload it and try again.")
        return Opportunity.model_validate(row)

    return router
