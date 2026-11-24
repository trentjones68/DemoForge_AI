"""Tenant-scoped requirements, gap review, and approved downstream inputs."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, RowMapping, text

from demoforge_api.analysis.routes import Approval
from demoforge_api.analysis.schema import StrictModel
from demoforge_api.auth import TokenVerifier
from demoforge_api.discovery.routes import (
    PAGE_SIZE,
    Scope,
    SessionScope,
    opportunity_access,
    read_body,
    workspace_lock,
)
from demoforge_api.planning.models import (
    MAX_ITEMS,
    MAX_LINKS,
    ApprovedRequirement,
    CreateItem,
    EditItem,
    Fields,
    Normalized,
    Plan,
    PlanItem,
    PlanRevision,
)
from demoforge_api.planning.normalizer import ApprovedInsight, Kind, RequirementsNormalizer
from demoforge_api.request_access import access_dependencies

BASE = "/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}"
MAX_INSIGHTS = 100

PLAN_READ = """
    SELECT p.*, p.normalization_key IS NOT NULL AS generated,
           COALESCE(affected.ids, '[]'::jsonb) AS affected_requirement_ids,
           COALESCE(citations.items, '[]'::jsonb) AS evidence
    FROM demoforge.current_plan_items p
    LEFT JOIN LATERAL (
        SELECT jsonb_agg(a.requirement_id ORDER BY a.requirement_id) AS ids
        FROM demoforge.plan_affected_requirements a
        WHERE (a.workspace_id, a.session_id, a.item_id, a.revision) =
              (p.workspace_id, p.session_id, p.id, p.revision)
    ) affected ON true
    LEFT JOIN LATERAL (
        SELECT jsonb_agg(jsonb_build_object(
            'source_id', c.source_id, 'segment_id', c.segment_id,
            'page', 1 + s.ordinal / :page_size,
            'quote', substring(s.text FROM c.quote_start + 1 FOR c.quote_end - c.quote_start)
        ) ORDER BY c.source_id, s.ordinal, c.quote_start) AS items
        FROM demoforge.analysis_citations c
        JOIN demoforge.transcript_segments s
          ON (s.workspace_id, s.session_id, s.source_id, s.id) =
             (c.workspace_id, c.session_id, c.source_id, c.segment_id)
        WHERE (c.workspace_id, c.session_id, c.job_id, c.finding_id, c.revision) =
              (p.workspace_id, p.session_id, p.source_job_id, p.source_finding_id,
               p.source_revision)
    ) citations ON true
    WHERE p.workspace_id = :workspace AND p.session_id = :session
"""

PLAN_ORDER = """
    ORDER BY CASE WHEN p.status = 'resolved' THEN 1 ELSE 0 END,
             CASE p.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
             p.created_at, p.id
"""


def owner_ids(connection: Connection, scope: SessionScope) -> list[UUID]:
    return list(
        connection.execute(
            text("SELECT id FROM demoforge.plan_owners(:workspace)"), scope.bindings
        ).scalars()
    )


def overview(connection: Connection, scope: SessionScope) -> Plan:
    items = connection.execute(
        text(PLAN_READ + PLAN_ORDER), scope.bindings | {"page_size": PAGE_SIZE}
    ).mappings()
    has_approved = connection.execute(
        text("""
        SELECT EXISTS (
            SELECT FROM demoforge.current_approved_findings
            WHERE workspace_id = :workspace AND session_id = :session
        )
    """),
        scope.bindings,
    ).scalar_one()
    return Plan(
        items=[PlanItem.model_validate(row) for row in items],
        owners=owner_ids(connection, scope),
        has_approved_insights=has_approved,
    )


def get_item(connection: Connection, scope: SessionScope, item_id: UUID) -> PlanItem:
    row = (
        connection.execute(
            text(PLAN_READ + " AND p.id = :id"),
            scope.bindings | {"id": item_id, "page_size": PAGE_SIZE},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Planning item not found.")
    return PlanItem.model_validate(row)


def validate_fields(connection: Connection, scope: SessionScope, kind: Kind, data: Fields) -> None:
    if "\x00" in data.statement or "\x00" in data.rationale:
        raise HTTPException(422, "Use plain text for the statement and rationale.")
    if kind == "requirement":
        if data.owner_id is not None or data.status is not None or data.affected_requirement_ids:
            raise HTTPException(422, "Owner, status and affected requirements apply to gaps.")
        return
    if data.status is None:
        raise HTTPException(422, "Select a status for the gap.")
    if data.owner_id is not None and data.owner_id not in owner_ids(connection, scope):
        raise HTTPException(422, "Choose an eligible owner in this workspace.")
    ids = data.affected_requirement_ids
    if ids:
        valid = connection.execute(
            text("""
            SELECT count(*) FROM demoforge.plan_items
            WHERE workspace_id = :workspace AND session_id = :session
              AND kind = 'requirement' AND id = ANY(:ids)
        """),
            scope.bindings | {"ids": ids},
        ).scalar_one()
        if valid != len(ids):
            raise HTTPException(422, "Select distinct requirements from this discovery session.")


def append_revision(
    connection: Connection,
    scope: SessionScope,
    item: UUID,
    kind: Kind,
    version: int,
    data: Fields,
) -> None:
    params = scope.bindings | {
        "id": item,
        "kind": kind,
        "version": version,
        "statement": data.statement,
        "rationale": data.rationale,
        "category": data.category,
        "priority": data.priority,
        "owner_id": data.owner_id,
        "status": data.status,
    }
    connection.execute(
        text("""
        INSERT INTO demoforge.plan_revisions
            (workspace_id, session_id, item_id, kind, revision, statement, rationale,
             category, priority, owner_id, status)
        VALUES (:workspace, :session, :id, :kind, :version, :statement, :rationale,
                :category, :priority, :owner_id, :status)
    """),
        params,
    )
    if data.affected_requirement_ids:
        connection.execute(
            text("""
            INSERT INTO demoforge.plan_affected_requirements
                (workspace_id, session_id, item_id, revision, requirement_id)
            VALUES (:workspace, :session, :id, :version, :target)
        """),
            [params | {"target": target} for target in data.affected_requirement_ids],
        )


def create_item(
    connection: Connection,
    scope: SessionScope,
    kind: Kind,
    data: Fields,
    key: str | None = None,
    source: ApprovedInsight | None = None,
) -> UUID:
    item = uuid4()
    connection.execute(
        text("""
        INSERT INTO demoforge.plan_items (
            workspace_id, session_id, id, kind, normalization_key,
            source_job_id, source_finding_id, source_revision
        ) VALUES (:workspace, :session, :id, :kind, :key, :job, :finding, :source_revision)
    """),
        scope.bindings
        | {
            "id": item,
            "kind": kind,
            "key": key,
            "job": source.job_id if source else None,
            "finding": source.id if source else None,
            "source_revision": source.revision if source else None,
        },
    )
    append_revision(connection, scope, item, kind, 1, data)
    return item


def capacity(current: int, added: int) -> None:
    if current + added > MAX_ITEMS:
        raise HTTPException(409, "This discovery session has reached its planning item limit.")


def normalize(connection: Connection, scope: SessionScope) -> Normalized:
    approved = (
        connection.execute(
            text("""
        SELECT job_id, id, revision, kind, classification, statement
        FROM demoforge.current_approved_findings
        WHERE workspace_id = :workspace AND session_id = :session
        ORDER BY job_id, id LIMIT :limit
    """),
            scope.bindings | {"limit": MAX_INSIGHTS + 1},
        )
        .mappings()
        .all()
    )
    if not approved:
        raise HTTPException(409, "Approve a discovery finding before generating drafts.")
    if len(approved) > MAX_INSIGHTS:
        raise HTTPException(409, "Use a smaller discovery session to normalize these findings.")
    existing = (
        connection.execute(
            text("""
        SELECT id, kind, category, normalization_key, stale_source
        FROM demoforge.current_plan_items
        WHERE workspace_id = :workspace AND session_id = :session
        ORDER BY created_at, id
    """),
            scope.bindings,
        )
        .mappings()
        .all()
    )
    keys = {item["normalization_key"] for item in existing}
    drafts = [
        draft
        for draft in RequirementsNormalizer().normalize(
            [ApprovedInsight(**row) for row in approved]
        )
        if draft.key not in keys
    ]
    capacity(len(existing), len(drafts))
    requirements = [
        (item["id"], item["category"])
        for item in existing
        if item["kind"] == "requirement" and not item["stale_source"]
    ]
    for draft in drafts:
        related = [
            target
            for target, category in requirements
            if draft.kind == "gap" and (draft.category == "general" or draft.category == category)
        ][:MAX_LINKS]
        item = create_item(
            connection,
            scope,
            draft.kind,
            Fields(
                statement=draft.statement,
                rationale=draft.rationale,
                priority=draft.priority,
                category=draft.category,
                status="open" if draft.kind == "gap" else None,
                affected_requirement_ids=related,
            ),
            key=draft.key,
            source=draft.source,
        )
        if draft.kind == "requirement":
            requirements.append((item, draft.category))
    return Normalized(added=len(drafts))


def history(connection: Connection, scope: SessionScope, item: UUID) -> list[RowMapping]:
    return list(
        connection.execute(
            text("""
        SELECT r.*, a.actor_id AS approved_by, a.approved_at,
               ARRAY(
                   SELECT ar.requirement_id FROM demoforge.plan_affected_requirements ar
                   WHERE (ar.workspace_id, ar.session_id, ar.item_id, ar.revision) =
                         (r.workspace_id, r.session_id, r.item_id, r.revision)
                   ORDER BY ar.requirement_id
               ) AS affected_requirement_ids
        FROM demoforge.plan_revisions r
        LEFT JOIN demoforge.plan_approvals a
          ON (a.workspace_id, a.session_id, a.item_id, a.revision) =
             (r.workspace_id, r.session_id, r.item_id, r.revision)
        WHERE r.workspace_id = :workspace AND r.session_id = :session AND r.item_id = :id
        ORDER BY r.revision DESC LIMIT 50
    """),
            scope.bindings | {"id": item},
        ).mappings()
    )


async def plan_body[Model: StrictModel](request: Request, model: type[Model]) -> Model:
    raw = await read_body(request, 12_288)
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Check the planning fields and revision.") from None


def planning_router(engine: Engine | None, verifier: TokenVerifier) -> APIRouter:
    router = APIRouter(prefix=BASE, tags=["planning"])
    path = "/discovery/{session_id}/plan"
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]

    async def create_body(request: Request, _: Actor) -> CreateItem:
        return await plan_body(request, CreateItem)

    async def edit_body(request: Request, _: Actor) -> EditItem:
        return await plan_body(request, EditItem)

    async def approval_body(request: Request, _: Actor) -> Approval:
        return await plan_body(request, Approval)

    def write_scope(connection: Connection, scope: SessionScope, actor: UUID) -> None:
        scope.authorize(connection, actor, write=True)
        # Shared with finding approval and discovery writes for a consistent source snapshot.
        workspace_lock(connection, scope.workspace_id)

    @router.get(path)
    def list_plan(scope: Scope, actor: Actor, connection: Database) -> Plan:
        scope.authorize(connection, actor)
        return overview(connection, scope)

    @router.post(path + "/normalize")
    def generate(scope: Scope, actor: Actor, connection: Database) -> Normalized:
        write_scope(connection, scope, actor)
        return normalize(connection, scope)

    @router.post(path + "/items", status_code=201)
    def add(
        scope: Scope,
        actor: Actor,
        connection: Database,
        data: Annotated[CreateItem, Depends(create_body)],
    ) -> PlanItem:
        write_scope(connection, scope, actor)
        current = connection.execute(
            text("""
            SELECT count(*) FROM demoforge.plan_items
            WHERE workspace_id = :workspace AND session_id = :session
        """),
            scope.bindings,
        ).scalar_one()
        capacity(current, 1)
        validate_fields(connection, scope, data.kind, data)
        return get_item(connection, scope, create_item(connection, scope, data.kind, data))

    @router.put(path + "/items/{item_id}")
    def edit(
        scope: Scope,
        actor: Actor,
        connection: Database,
        item_id: UUID,
        data: Annotated[EditItem, Depends(edit_body)],
    ) -> PlanItem:
        write_scope(connection, scope, actor)
        item = get_item(connection, scope, item_id)
        if item.revision != data.revision:
            raise HTTPException(409, "This item changed. Refresh and review the current revision.")
        validate_fields(connection, scope, item.kind, data)
        append_revision(connection, scope, item_id, item.kind, item.revision + 1, data)
        return get_item(connection, scope, item_id)

    @router.post(path + "/items/{item_id}/approve")
    def approve(
        scope: Scope,
        actor: Actor,
        connection: Database,
        item_id: UUID,
        data: Annotated[Approval, Depends(approval_body)],
    ) -> PlanItem:
        write_scope(connection, scope, actor)
        item = get_item(connection, scope, item_id)
        if item.revision != data.revision:
            raise HTTPException(409, "This item changed. Refresh and review the current revision.")
        if item.stale_source:
            raise HTTPException(
                409, "The source finding changed. Generate drafts from fresh approvals."
            )
        connection.execute(
            text("""
            INSERT INTO demoforge.plan_approvals (workspace_id, session_id, item_id, revision)
            VALUES (:workspace, :session, :id, :revision) ON CONFLICT DO NOTHING
        """),
            scope.bindings | {"id": item_id, "revision": item.revision},
        )
        return get_item(connection, scope, item_id)

    @router.get(path + "/items/{item_id}/history")
    def revisions(
        scope: Scope, actor: Actor, connection: Database, item_id: UUID
    ) -> list[PlanRevision]:
        scope.authorize(connection, actor)
        rows = history(connection, scope, item_id)
        if not rows:
            raise HTTPException(404, "Planning item not found.")
        return [PlanRevision.model_validate(row) for row in rows]

    @router.get("/approved-requirements")
    def approved_inputs(
        workspace_id: UUID, opportunity_id: UUID, actor: Actor, connection: Database
    ) -> list[ApprovedRequirement]:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=False)
        rows = connection.execute(
            text("""
            SELECT * FROM demoforge.approved_storyboard_requirements
            WHERE workspace_id = :workspace AND opportunity_id = :opportunity
            ORDER BY session_id, id
        """),
            {"workspace": workspace_id, "opportunity": opportunity_id},
        ).mappings()
        return [ApprovedRequirement.model_validate(row) for row in rows]

    return router
