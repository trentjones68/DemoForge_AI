"""Authenticated readiness, preparation sign-offs, and audited file delivery."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import Connection, Engine, text

from demoforge_api.auth import TokenVerifier
from demoforge_api.discovery.routes import opportunity_access, workspace_lock
from demoforge_api.exports.document import storyboard_document
from demoforge_api.exports.readiness import (
    PrepTask,
    PrepUpdate,
    Readiness,
    preparation_states,
    readiness_for,
)
from demoforge_api.exports.render import ExportBoundsError, ExportFontsError, ExportFormat, render
from demoforge_api.opportunities import get_record
from demoforge_api.request_access import access_dependencies
from demoforge_api.storyboard.models import MAX_REVISIONS
from demoforge_api.storyboard.routes import payload
from demoforge_api.storyboard.store import Scope, load_studio

RevisionQuery = Annotated[int, Query(ge=1, le=MAX_REVISIONS)]


def record_download(
    connection: Connection, scope: Scope, readiness: Readiness, fmt: ExportFormat, size: int
) -> None:
    connection.execute(
        text("""
        INSERT INTO demoforge.storyboard_export_events (
            workspace_id, opportunity_id, storyboard_id, revision, delivery_id, event, format,
            byte_count, demo_ready
        ) VALUES
            (:workspace, :opportunity, :storyboard, :revision, :delivery, 'export_generated',
             :format, :size, :ready),
            (:workspace, :opportunity, :storyboard, :revision, :delivery, 'artifact_accessed',
             :format, :size, :ready)
    """),
        scope
        | {
            "revision": readiness.revision,
            "delivery": uuid4(),
            "format": fmt,
            "size": size,
            "ready": readiness.ready,
        },
    )


def export_router(engine: Engine | None, verifier: TokenVerifier, origin: str) -> APIRouter:
    router = APIRouter(
        prefix="/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/storyboards/{storyboard_id}",
        tags=["storyboard exports"],
    )
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]

    def reader(
        workspace_id: UUID,
        opportunity_id: UUID,
        storyboard_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> Scope:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=False)
        return {
            "workspace": workspace_id,
            "opportunity": opportunity_id,
            "storyboard": storyboard_id,
        }

    def writer(
        workspace_id: UUID,
        opportunity_id: UUID,
        storyboard_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> Scope:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=True)
        return {
            "workspace": workspace_id,
            "opportunity": opportunity_id,
            "storyboard": storyboard_id,
        }

    Read = Annotated[Scope, Depends(reader)]
    Write = Annotated[Scope, Depends(writer)]

    async def prep_body(request: Request, _: Actor) -> PrepUpdate:
        return await payload(request, PrepUpdate)

    @router.get("/readiness")
    def readiness(scope: Read, connection: Database, revision: RevisionQuery) -> Readiness:
        workspace_lock(connection, scope["workspace"])
        studio = load_studio(connection, scope, revision)
        opportunity = get_record(connection, scope["workspace"], scope["opportunity"])
        return readiness_for(connection, scope, studio, opportunity)

    @router.put("/readiness/{task}")
    def prepare(
        task: PrepTask,
        scope: Write,
        connection: Database,
        data: Annotated[PrepUpdate, Depends(prep_body)],
    ) -> Readiness:
        workspace_lock(connection, scope["workspace"])
        studio = load_studio(connection, scope)
        if studio.current_revision != data.revision:
            raise HTTPException(
                409, "The storyboard changed. Open its current revision to update prep."
            )
        opportunity = get_record(connection, scope["workspace"], scope["opportunity"])
        if opportunity.archived_at:
            raise HTTPException(409, "Archived opportunities are read only.")
        if preparation_states(connection, scope, data.revision).get(task, False) != data.complete:
            connection.execute(
                text("""
                INSERT INTO demoforge.storyboard_prep_events (
                    workspace_id, opportunity_id, storyboard_id, revision, task, complete
                ) VALUES (:workspace, :opportunity, :storyboard, :revision, :task, :complete)
            """),
                scope | {"revision": data.revision, "task": task, "complete": data.complete},
            )
        return readiness_for(connection, scope, studio, opportunity)

    @router.get("/export", response_class=Response)
    def download(
        scope: Read,
        connection: Database,
        revision: RevisionQuery,
        fmt: Annotated[ExportFormat, Query(alias="format")],
    ) -> Response:
        workspace_lock(connection, scope["workspace"])
        studio = load_studio(connection, scope, revision)
        board = studio.storyboard
        if board.approved_at is None:
            raise HTTPException(409, "Approve this storyboard revision before exporting it.")
        opportunity = get_record(connection, scope["workspace"], scope["opportunity"])
        ready = readiness_for(connection, scope, studio, opportunity)
        try:
            content = render(storyboard_document(opportunity, board, ready, origin), fmt)
        except ExportBoundsError:
            raise HTTPException(
                413,
                "The storyboard exceeds export limits. Shorten its content and approve the update.",
            ) from None
        except ExportFontsError:
            raise HTTPException(
                503, "PDF fonts are unavailable. Try Markdown or contact your administrator."
            ) from None
        record_download(connection, scope, ready, fmt, len(content))
        filename = f"demo-storyboard-{board.id}-r{revision}.{fmt}"
        return Response(
            content,
            media_type="application/pdf" if fmt == "pdf" else "text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

    return router
