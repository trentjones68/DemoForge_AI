"""Tenant-scoped run history and optimistic evidence review."""

from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Connection, Engine, RowMapping, text

from demoforge_api.analysis.provider import FAKE_MODEL, OPENAI_MODEL
from demoforge_api.analysis.schema import (
    PROMPT_VERSION,
    EvidenceClass,
    FailureCode,
    FindingKind,
    Statement,
    StrictModel,
)
from demoforge_api.auth import TokenVerifier
from demoforge_api.discovery.routes import PAGE_SIZE, Scope, SessionScope, read_body, workspace_lock
from demoforge_api.request_access import access_dependencies
from demoforge_api.settings import Settings

RunStatus = Literal["queued", "running", "succeeded", "failed"]
Revision = Annotated[int, Field(ge=1, le=2147483645)]


class Run(BaseModel):
    id: UUID
    status: RunStatus
    attempts: int
    error_code: FailureCode | None
    provider: Literal["openai", "fake"]
    model: str
    prompt_version: str
    created_at: datetime


class Overview(BaseModel):
    enabled: bool
    runs: list[Run]


class Citation(BaseModel):
    source_id: UUID
    segment_id: UUID
    page: int
    quote: str


class Finding(BaseModel):
    id: UUID
    revision: int
    kind: FindingKind
    classification: EvidenceClass
    statement: str
    rationale: str
    confidence: float
    editor_id: UUID | None
    approved_at: datetime | None
    approved_by: UUID | None
    evidence: list[Citation]


class Review(BaseModel):
    run: Run
    findings: list[Finding]


class Approval(StrictModel):
    revision: Revision


class Edit(Approval):
    statement: Statement
    rationale: Statement


def get_run(connection: Connection, scope: SessionScope, run_id: UUID) -> Run:
    row = (
        connection.execute(
            text("""
            SELECT * FROM demoforge.analysis_jobs
            WHERE workspace_id = :workspace AND session_id = :session AND id = :job
        """),
            scope.bindings | {"job": run_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Analysis run not found")
    return Run.model_validate(row)


def enqueue(connection: Connection, scope: SessionScope, provider: str) -> Run:
    pending = (
        connection.execute(
            text("""
            SELECT * FROM demoforge.analysis_jobs
            WHERE workspace_id = :workspace AND session_id = :session
              AND status IN ('queued','running')
        """),
            scope.bindings,
        )
        .mappings()
        .one_or_none()
    )
    if pending:
        return Run.model_validate(pending)
    sources = list(
        connection.execute(
            text("""
            SELECT id FROM demoforge.source_documents
            WHERE workspace_id = :workspace AND session_id = :session
              AND status = 'ready' AND kind = 'transcript'
            ORDER BY id
        """),
            scope.bindings,
        ).scalars()
    )
    if not sources:
        raise HTTPException(409, "Import a transcript before running discovery analysis.")
    model = OPENAI_MODEL if provider == "openai" else FAKE_MODEL
    digest = sha256("".join(str(source) for source in sources).encode()).hexdigest()
    params = scope.bindings | {
        "hash": digest,
        "provider": provider,
        "model": model,
        "prompt": PROMPT_VERSION,
    }
    existing = (
        connection.execute(
            text("""
            SELECT * FROM demoforge.analysis_jobs
            WHERE workspace_id = :workspace AND session_id = :session AND input_hash = :hash
              AND provider = :provider AND model = :model AND prompt_version = :prompt
        """),
            params,
        )
        .mappings()
        .one_or_none()
    )
    if existing:
        return Run.model_validate(existing)

    available = connection.execute(
        text("""
            SELECT count(*) FILTER (WHERE created_at >= statement_timestamp() - interval '24 h')
                   < 20 AND count(*) FILTER (WHERE status IN ('queued','running')) < 3
            FROM demoforge.analysis_jobs WHERE workspace_id = :workspace
        """),
        scope.bindings,
    ).scalar_one()
    if not available:
        raise HTTPException(429, "Workspace analysis limit reached. Try again later.")
    job = uuid4()
    row = (
        connection.execute(
            text("""
            INSERT INTO demoforge.analysis_jobs (
                workspace_id, session_id, id, input_hash, provider, model, prompt_version
            ) VALUES (:workspace, :session, :job, :hash, :provider, :model, :prompt)
            RETURNING *
        """),
            params | {"job": job},
        )
        .mappings()
        .one()
    )
    connection.execute(
        text("""
            INSERT INTO demoforge.analysis_sources (workspace_id, session_id, job_id, source_id)
            VALUES (:workspace, :session, :job, :source)
        """),
        [scope.bindings | {"job": job, "source": source} for source in sources],
    )
    return Run.model_validate(row)


def review_run(connection: Connection, scope: SessionScope, run: Run) -> Review:
    if run.status != "succeeded":
        return Review(run=run, findings=[])
    params = scope.bindings | {"job": run.id}
    rows = connection.execute(
        text("""
        WITH latest AS (
            SELECT DISTINCT ON (f.id) f.*, a.approved_at, a.actor_id AS approved_by
            FROM demoforge.analysis_findings f
            LEFT JOIN demoforge.analysis_approvals a ON
                (a.workspace_id, a.session_id, a.job_id, a.finding_id, a.revision) =
                (f.workspace_id, f.session_id, f.job_id, f.id, f.revision)
            WHERE f.workspace_id = :workspace AND f.session_id = :session AND f.job_id = :job
            ORDER BY f.id, f.revision DESC
        )
        SELECT latest.*, coalesce(evidence.items, '[]'::jsonb) AS evidence
        FROM latest
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object(
                'source_id', c.source_id, 'segment_id', c.segment_id,
                'page', 1 + s.ordinal / :page_size,
                'quote', substring(s.text FROM c.quote_start + 1 FOR c.quote_end - c.quote_start)
            ) ORDER BY c.source_id, s.ordinal, c.quote_start) AS items
            FROM demoforge.analysis_citations c
            JOIN demoforge.transcript_segments s ON
                (s.workspace_id, s.session_id, s.source_id, s.id) =
                (c.workspace_id, c.session_id, c.source_id, c.segment_id)
            WHERE (c.workspace_id, c.session_id, c.job_id, c.finding_id, c.revision) =
                (latest.workspace_id, latest.session_id, latest.job_id, latest.id, latest.revision)
        ) evidence ON true
        ORDER BY latest.created_at, latest.id
    """),
        params | {"page_size": PAGE_SIZE},
    ).mappings()
    return Review(run=run, findings=[Finding.model_validate(row) for row in rows])


def current_revision(connection: Connection, params: dict[str, UUID], expected: int) -> RowMapping:
    row = (
        connection.execute(
            text("""
        SELECT * FROM demoforge.analysis_findings
        WHERE workspace_id = :workspace AND session_id = :session AND job_id = :job AND id = :id
        ORDER BY revision DESC LIMIT 1
    """),
            params,
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Finding not found")
    if row["revision"] != expected:
        raise HTTPException(409, "The finding changed. Refresh and review the current revision.")
    return row


async def review_body[Model: Approval](request: Request, schema: type[Model]) -> Model:
    raw = await read_body(request, 12_288)
    try:
        return schema.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid review fields or revision.") from None


def analysis_router(
    engine: Engine | None, verifier: TokenVerifier, settings: Settings
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/discovery/"
        "{session_id}/analysis",
        tags=["analysis"],
    )
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]
    provider = settings.discovery_provider

    async def edit_body(request: Request, _: Actor) -> Edit:
        return await review_body(request, Edit)

    async def approval_body(request: Request, _: Actor) -> Approval:
        return await review_body(request, Approval)

    @router.get("")
    def overview(scope: Scope, actor: Actor, connection: Database) -> Overview:
        scope.authorize(connection, actor)
        rows = connection.execute(
            text("""
            SELECT * FROM demoforge.analysis_jobs
            WHERE workspace_id = :workspace AND session_id = :session
            ORDER BY created_at DESC, id LIMIT 20
        """),
            scope.bindings,
        ).mappings()
        return Overview(
            enabled=provider != "disabled", runs=[Run.model_validate(row) for row in rows]
        )

    @router.post("", status_code=202)
    def start(scope: Scope, actor: Actor, connection: Database) -> Run:
        scope.authorize(connection, actor, write=True)
        if provider == "disabled":
            raise HTTPException(503, "Discovery analysis is disabled.")
        workspace_lock(connection, scope.workspace_id)
        return enqueue(connection, scope, provider)

    @router.get("/{job_id}")
    def detail(scope: Scope, actor: Actor, connection: Database, job_id: UUID) -> Review:
        scope.authorize(connection, actor)
        return review_run(connection, scope, get_run(connection, scope, job_id))

    @router.put("/{job_id}/findings/{finding_id}")
    def edit(
        scope: Scope,
        actor: Actor,
        connection: Database,
        job_id: UUID,
        finding_id: UUID,
        body: Annotated[Edit, Depends(edit_body)],
    ) -> Review:
        scope.authorize(connection, actor, write=True)
        workspace_lock(connection, scope.workspace_id)
        run = get_run(connection, scope, job_id)
        if "\x00" in body.statement + body.rationale:
            raise HTTPException(422, "Use plain text for the finding and rationale.")
        params = scope.bindings | {"job": job_id, "id": finding_id}
        row = current_revision(connection, params, body.revision)
        changes = params | {
            "revision": body.revision,
            "kind": row["kind"],
            "class": row["classification"],
            "statement": body.statement,
            "rationale": body.rationale,
            "confidence": row["confidence"],
            "actor": actor,
        }
        connection.execute(
            text("""
            INSERT INTO demoforge.analysis_findings (
                workspace_id, session_id, job_id, id, revision, kind, classification,
                statement, rationale, confidence, editor_id
            ) VALUES (
                :workspace, :session, :job, :id, :revision + 1, :kind, :class,
                :statement, :rationale, :confidence, :actor
            )
        """),
            changes,
        )
        connection.execute(
            text("""
            INSERT INTO demoforge.analysis_citations
                (workspace_id, session_id, job_id, finding_id, revision,
                 source_id, segment_id, quote_start, quote_end)
            SELECT workspace_id, session_id, job_id, finding_id, revision + 1,
                   source_id, segment_id, quote_start, quote_end
            FROM demoforge.analysis_citations
            WHERE workspace_id = :workspace AND session_id = :session AND job_id = :job
              AND finding_id = :id AND revision = :revision
        """),
            changes,
        )
        return review_run(connection, scope, run)

    @router.post("/{job_id}/findings/{finding_id}/approve")
    def approve(
        scope: Scope,
        actor: Actor,
        connection: Database,
        job_id: UUID,
        finding_id: UUID,
        body: Annotated[Approval, Depends(approval_body)],
    ) -> Review:
        scope.authorize(connection, actor, write=True)
        workspace_lock(connection, scope.workspace_id)
        run = get_run(connection, scope, job_id)
        params = scope.bindings | {"job": job_id, "id": finding_id}
        current_revision(connection, params, body.revision)
        connection.execute(
            text("""
            INSERT INTO demoforge.analysis_approvals
                (workspace_id, session_id, job_id, finding_id, revision)
            VALUES (:workspace, :session, :job, :id, :revision)
            ON CONFLICT DO NOTHING
        """),
            params | {"revision": body.revision},
        )
        return review_run(connection, scope, run)

    return router
