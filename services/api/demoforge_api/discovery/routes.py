"""Authorized ingestion and read-only evidence locators."""

from asyncio import timeout
from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from sqlalchemy import Connection, Engine, text
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from demoforge_api.auth import TokenVerifier
from demoforge_api.discovery.imports import (
    ManualPlaudExport,
    Method,
    Original,
    PlaudImportAdapter,
    Provider,
    Segment,
    SourceKind,
    manual_original,
    parse_original,
    segment_text,
)
from demoforge_api.discovery.parser import MAX_UPLOAD
from demoforge_api.discovery.storage import DiscoveryStorage, object_key
from demoforge_api.opportunities import Opportunity, get_record, require_writer
from demoforge_api.request_access import access_dependencies, actor_transaction
from demoforge_api.workspaces import Role, find_workspace

PAGE_SIZE = 50
UPLOAD_SLOTS = BoundedSemaphore(8)


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    occurred_on: date | None = None


class Session(BaseModel):
    id: UUID
    title: str
    occurred_on: date | None
    created_at: datetime


class Source(BaseModel):
    id: UUID
    kind: SourceKind
    provider: Provider
    method: Method
    format: str
    filename: str | None
    byte_count: int
    consent_at: datetime


class Imported(BaseModel):
    source: Source
    duplicate: bool


class SourceSegment(BaseModel):
    id: UUID
    ordinal: int
    start_offset: int
    end_offset: int
    text: str
    speaker: str | None
    start_ms: int | None
    end_ms: int | None


class EvidencePage(BaseModel):
    source: Source
    segments: list[SourceSegment]
    has_next: bool


class Download(BaseModel):
    url: str


async def read_body(request: Request, maximum: int) -> bytes:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            declared = int(length)
        except ValueError:
            raise HTTPException(400, "Invalid source length.") from None
        if declared < 0:
            raise HTTPException(400, "Invalid source length.")
        if declared > maximum:
            raise HTTPException(413, "The request exceeds the allowed size.")
    data = bytearray()
    try:
        async with timeout(12):
            async for chunk in request.stream():
                if len(data) + len(chunk) > maximum:
                    raise HTTPException(413, "The request exceeds the allowed size.")
                data.extend(chunk)
    except (TimeoutError, ClientDisconnect):
        raise HTTPException(
            408, "The upload was interrupted. Retry with the same source."
        ) from None
    return bytes(data)


def opportunity_access(
    connection: Connection, workspace_id: UUID, opportunity_id: UUID, actor: UUID, write: bool
) -> Opportunity:
    workspace = find_workspace(connection, workspace_id, actor)
    if workspace.role not in (Role.ADMIN, Role.SALES_ENGINEER):
        raise HTTPException(403, "Your workspace role cannot access discovery records.")
    opportunity = get_record(connection, workspace_id, opportunity_id)
    if write:
        require_writer(workspace.role, actor, opportunity.owner_id)
        if opportunity.archived_at is not None:
            raise HTTPException(409, "Archived opportunities are read only")
    return opportunity


@dataclass(frozen=True)
class SessionScope:
    workspace_id: UUID
    opportunity_id: UUID
    session_id: UUID

    @property
    def bindings(self) -> dict[str, UUID]:
        return {"workspace": self.workspace_id, "session": self.session_id}

    def authorize(self, connection: Connection, actor: UUID, write: bool = False) -> None:
        opportunity_access(connection, self.workspace_id, self.opportunity_id, actor, write)
        exists = connection.execute(
            text("""
                SELECT 1 FROM demoforge.discovery_sessions
                WHERE workspace_id = :workspace AND opportunity_id = :opportunity AND id = :session
            """),
            self.bindings | {"opportunity": self.opportunity_id},
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(404, "Discovery session not found")

    def object_key(self, source: Source) -> str:
        return object_key(self.workspace_id, self.session_id, source.id, source.format)


Scope = Annotated[SessionScope, Depends(SessionScope)]


def workspace_lock(connection: Connection, workspace: UUID) -> None:
    # Serialize quota checks and finalization without holding a lock during parsing or storage.
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"demoforge:discovery:{workspace}"},
    )


def discovery_router(
    engine: Engine | None, verifier: TokenVerifier, storage: DiscoveryStorage
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/discovery",
        tags=["discovery"],
    )
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]
    plaud: PlaudImportAdapter = ManualPlaudExport()

    @router.get("")
    def list_sessions(
        workspace_id: UUID, opportunity_id: UUID, actor: Actor, connection: Database
    ) -> list[Session]:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=False)
        rows = connection.execute(
            text("""
                SELECT * FROM demoforge.discovery_sessions
                WHERE workspace_id = :workspace AND opportunity_id = :opportunity
                ORDER BY created_at DESC, id
            """),
            {"workspace": workspace_id, "opportunity": opportunity_id},
        ).mappings()
        return [Session.model_validate(row) for row in rows]

    @router.post("", status_code=201)
    async def create_session(
        workspace_id: UUID, opportunity_id: UUID, actor: Actor, request: Request
    ) -> Session:
        mime = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if mime != "application/json":
            raise HTTPException(415, "Send session details as JSON.")
        raw = await read_body(request, 2048)
        try:
            session = NewSession.model_validate_json(raw)
        except ValidationError:
            raise HTTPException(422, "Enter a title and an optional date in YYYY-MM-DD format.")
        if "\x00" in session.title:
            raise HTTPException(422, "Use a plain-text session title.")
        return await run_in_threadpool(
            create_session_record, engine, workspace_id, opportunity_id, actor, session
        )

    @router.get("/{session_id}/sources")
    def list_sources(scope: Scope, actor: Actor, connection: Database) -> list[Source]:
        scope.authorize(connection, actor)
        rows = connection.execute(
            text("""
                SELECT * FROM demoforge.source_documents
                WHERE workspace_id = :workspace AND session_id = :session AND status = 'ready'
                ORDER BY consent_at, id
            """),
            scope.bindings,
        ).mappings()
        return [Source.model_validate(row) for row in rows]

    @router.post("/{session_id}/sources", status_code=201, responses={200: {"model": Imported}})
    async def import_source(
        scope: Scope,
        actor: Actor,
        request: Request,
        response: Response,
        kind: Annotated[SourceKind, Query()] = "transcript",
        provider: Annotated[Provider, Query()] = "manual",
    ) -> Imported:
        await run_in_threadpool(preflight, engine, scope, actor)
        if request.headers.get("x-import-consent") != "true":
            raise HTTPException(422, "Confirm recording and import consent before uploading.")
        filename = request.headers.get("x-source-filename")
        mime = request.headers.get("content-type", "")
        original = (
            plaud.adapt(kind, filename, mime)
            if provider == "plaud"
            else manual_original(provider, kind, filename, mime)
        )
        storage.require_configured()
        if not UPLOAD_SLOTS.acquire(blocking=False):
            raise HTTPException(429, "Discovery uploads are busy. Try again shortly.")
        try:
            content = await read_body(request, MAX_UPLOAD)
            result = await run_in_threadpool(
                persist_import, engine, storage, scope, actor, original, content
            )
        finally:
            UPLOAD_SLOTS.release()
        if result.duplicate:
            response.status_code = 200
        return result

    @router.get("/{session_id}/sources/{source_id}/segments")
    def evidence(
        scope: Scope,
        actor: Actor,
        connection: Database,
        source_id: UUID,
        page: Annotated[int, Query(ge=1, le=60)] = 1,
    ) -> EvidencePage:
        scope.authorize(connection, actor)
        source = ready_source(connection, scope, source_id)
        rows = (
            connection.execute(
                text("""
                SELECT * FROM demoforge.transcript_segments
                WHERE workspace_id = :workspace AND session_id = :session AND source_id = :id
                ORDER BY ordinal LIMIT :limit OFFSET :offset
            """),
                scope.bindings
                | {"id": source_id, "limit": PAGE_SIZE + 1, "offset": (page - 1) * PAGE_SIZE},
            )
            .mappings()
            .all()
        )
        return EvidencePage(
            source=source,
            segments=[SourceSegment.model_validate(row) for row in rows[:PAGE_SIZE]],
            has_next=len(rows) > PAGE_SIZE,
        )

    @router.post("/{session_id}/sources/{source_id}/original")
    def sign_original(
        scope: Scope, actor: Actor, connection: Database, source_id: UUID
    ) -> Download:
        scope.authorize(connection, actor)
        source = ready_source(connection, scope, source_id)
        return Download(url=storage.sign(scope.object_key(source), source.format))

    return router


def create_session_record(
    engine: Engine | None, workspace: UUID, opportunity: UUID, actor: UUID, session: NewSession
) -> Session:
    with actor_transaction(engine, actor) as connection:
        workspace_lock(connection, workspace)
        opportunity_access(connection, workspace, opportunity, actor, write=True)
        params = {"workspace": workspace, "opportunity": opportunity}
        count = connection.execute(
            text("""
                SELECT count(*) FROM demoforge.discovery_sessions
                WHERE workspace_id = :workspace AND opportunity_id = :opportunity
            """),
            params,
        ).scalar_one()
        if count >= 50:
            raise HTTPException(409, "This opportunity has reached its discovery session limit.")
        row = (
            connection.execute(
                text("""
                INSERT INTO demoforge.discovery_sessions
                    (workspace_id, opportunity_id, id, title, occurred_on)
                VALUES (:workspace, :opportunity, :id, :title, :occurred_on)
                RETURNING *
            """),
                params | {"id": uuid4()} | session.model_dump(),
            )
            .mappings()
            .one()
        )
        return Session.model_validate(row)


def preflight(engine: Engine | None, scope: SessionScope, actor: UUID) -> None:
    with actor_transaction(engine, actor) as connection:
        scope.authorize(connection, actor, write=True)


def ready_source(connection: Connection, scope: SessionScope, source_id: UUID) -> Source:
    row = (
        connection.execute(
            text("""
            SELECT * FROM demoforge.source_documents
            WHERE workspace_id = :workspace AND session_id = :session AND id = :id
                AND status = 'ready'
        """),
            scope.bindings | {"id": source_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Discovery source not found")
    return Source.model_validate(row)


def reserve_source(
    connection: Connection, scope: SessionScope, original: Original, content: bytes, digest: str
) -> tuple[Source, bool]:
    params = scope.bindings | {"kind": original.kind, "sha256": digest}
    row = (
        connection.execute(
            text("""
            SELECT * FROM demoforge.source_documents
            WHERE workspace_id = :workspace AND session_id = :session
                AND kind = :kind AND sha256 = :sha256
        """),
            params,
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        return Source.model_validate(row), row["status"] == "ready"

    byte_count = len(content)
    capacity = connection.execute(
        text("SELECT demoforge.discovery_upload_has_capacity(:workspace, :session, :byte_count)"),
        scope.bindings | {"byte_count": byte_count},
    ).scalar_one()
    if not capacity:
        raise HTTPException(409, "This session or workspace has reached its source storage limit.")
    row = (
        connection.execute(
            text("""
            INSERT INTO demoforge.source_documents (
                workspace_id, session_id, id, kind, provider, method, format, filename,
                sha256, byte_count
            ) VALUES (
                :workspace, :session, :id, :kind, :provider, :method, :format, :filename,
                :sha256, :byte_count
            )
            RETURNING *
        """),
            params | asdict(original) | {"id": uuid4(), "byte_count": byte_count},
        )
        .mappings()
        .one()
    )
    return Source.model_validate(row), False


def persist_import(
    engine: Engine | None,
    storage: DiscoveryStorage,
    scope: SessionScope,
    actor: UUID,
    original: Original,
    content: bytes,
) -> Imported:
    digest = sha256(content).hexdigest()
    segments = segment_text(parse_original(content, original.format))
    with actor_transaction(engine, actor) as connection:
        workspace_lock(connection, scope.workspace_id)
        scope.authorize(connection, actor, write=True)
        source, ready = reserve_source(connection, scope, original, content, digest)
        if ready:
            return Imported(source=source, duplicate=True)

    # A committed reservation always precedes the first storage request. A lost response or
    # interrupted completion can be retried with the same bytes and no object or evidence drift.
    storage.save(scope.object_key(source), source.format, content)
    with actor_transaction(engine, actor) as connection:
        workspace_lock(connection, scope.workspace_id)
        scope.authorize(connection, actor, write=True)
        duplicate = complete_source(connection, scope, source, segments)
    return Imported(source=source, duplicate=duplicate)


def complete_source(
    connection: Connection, scope: SessionScope, source: Source, segments: list[Segment]
) -> bool:
    params = scope.bindings | {"source": source.id}
    state = connection.execute(
        text("""
            SELECT status FROM demoforge.source_documents
            WHERE workspace_id = :workspace AND session_id = :session AND id = :source
        """),
        params,
    ).scalar_one_or_none()
    if state == "ready":
        return True
    if state != "pending":
        raise HTTPException(404, "Discovery source not found")

    connection.execute(
        text("""
            INSERT INTO demoforge.transcript_segments (
                workspace_id, session_id, source_id, id, ordinal, start_offset, end_offset,
                text, speaker, start_ms, end_ms
            ) VALUES (
                :workspace, :session, :source, :id, :ordinal, :start_offset, :end_offset,
                :text, :speaker, :start_ms, :end_ms
            )
        """),
        [params | asdict(segment) | {"id": segment.id(source.id)} for segment in segments],
    )
    updated = connection.execute(
        text("""
            UPDATE demoforge.source_documents SET status = 'ready'
            WHERE workspace_id = :workspace AND session_id = :session AND id = :source
            RETURNING id
        """),
        params,
    ).scalar_one_or_none()
    if updated is None:
        raise HTTPException(403, "Workspace action denied")
    return False
