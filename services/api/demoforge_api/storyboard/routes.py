"""Opportunity-scoped Demo Studio routes with optimistic revision checks."""

from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text

from demoforge_api.analysis.routes import Approval
from demoforge_api.analysis.schema import StrictModel
from demoforge_api.auth import TokenVerifier
from demoforge_api.catalog.routes import release_record
from demoforge_api.discovery.routes import opportunity_access, read_body, workspace_lock
from demoforge_api.request_access import access_dependencies
from demoforge_api.storyboard.models import (
    MAX_REVISIONS,
    MAX_STORYBOARDS,
    AgendaEdit,
    Brief,
    EditField,
    Generate,
    Proposal,
    ProposalAcceptance,
    RevisionAction,
    Scene,
    SceneCopy,
    SceneEdit,
    Storyboard,
    StoryboardApproval,
    StoryboardSummary,
    Studio,
)
from demoforge_api.storyboard.planner import StoryboardPlanner
from demoforge_api.storyboard.store import (
    OPPORTUNITY,
    Scope,
    append_revision,
    eligible_inputs,
    list_storyboards,
    load_studio,
)

FIELDS: tuple[EditField, ...] = (
    "title",
    "actions",
    "talk_track",
    "expected_outcome",
    "synthetic_data",
    "risks",
)


async def payload[Model: StrictModel](request: Request, model: type[Model]) -> Model:
    raw = await read_body(request, 128 * 1024)
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(
            422, "Check the required fields, lengths, timing, and storyboard revision."
        ) from None


def load_base(connection: Connection, scope: Scope, expected: int) -> Storyboard:
    workspace_lock(connection, scope["workspace"])
    board = load_studio(connection, scope).storyboard
    if board.revision != expected:
        raise HTTPException(
            409, "The storyboard changed. Reload the latest revision before continuing."
        )
    return board


def save(
    connection: Connection,
    scope: Scope,
    board: Storyboard,
    scenes: list[Scene],
    action: RevisionAction,
) -> Storyboard:
    if board.revision >= MAX_REVISIONS:
        raise HTTPException(
            409,
            "This storyboard reached its revision limit. Create another storyboard to continue.",
        )
    return append_revision(connection, scope, board.release.id, scenes, action, board.revision + 1)


def find_scene(board: Storyboard, scene_id: UUID) -> Scene:
    scene = next((scene for scene in board.scenes if scene.id == scene_id), None)
    if scene is None:
        raise HTTPException(404, "Storyboard scene not found.")
    return scene


def replacing(board: Storyboard, updated: Scene) -> list[Scene]:
    return [updated if scene.id == updated.id else scene for scene in board.scenes]


def preview(connection: Connection, scope: Scope, board: Storyboard, scene: Scene) -> Proposal:
    inputs = eligible_inputs(connection, scope | {"release": board.release.id}, scene=scene)
    generated = StoryboardPlanner().scene(board.brief, inputs[0], scene.minutes)
    candidate = generated.model_copy(update={"id": scene.id})
    fingerprint = sha256(
        f"{board.id}:{board.revision}:{candidate.model_dump_json()}".encode()
    ).hexdigest()
    return Proposal(scene=candidate, fingerprint=fingerprint)


def storyboard_router(engine: Engine | None, verifier: TokenVerifier) -> APIRouter:
    router = APIRouter(
        prefix="/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/storyboards",
        tags=["storyboards"],
    )
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]

    def reader(
        workspace_id: UUID, opportunity_id: UUID, actor: Actor, connection: Database
    ) -> Scope:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=False)
        return {"workspace": workspace_id, "opportunity": opportunity_id}

    def writer(
        workspace_id: UUID, opportunity_id: UUID, actor: Actor, connection: Database
    ) -> Scope:
        opportunity_access(connection, workspace_id, opportunity_id, actor, write=True)
        return {"workspace": workspace_id, "opportunity": opportunity_id}

    Read = Annotated[Scope, Depends(reader)]
    Write = Annotated[Scope, Depends(writer)]

    async def generate_body(request: Request, _: Actor) -> Generate:
        return await payload(request, Generate)

    async def edit_body(request: Request, _: Actor) -> SceneEdit:
        return await payload(request, SceneEdit)

    async def agenda_body(request: Request, _: Actor) -> AgendaEdit:
        return await payload(request, AgendaEdit)

    async def revision_body(request: Request, _: Actor) -> Approval:
        return await payload(request, Approval)

    async def apply_body(request: Request, _: Actor) -> ProposalAcceptance:
        return await payload(request, ProposalAcceptance)

    async def approval_body(request: Request, _: Actor) -> StoryboardApproval:
        return await payload(request, StoryboardApproval)

    @router.get("")
    def list_boards(scope: Read, connection: Database) -> list[StoryboardSummary]:
        return list_storyboards(connection, scope)

    @router.get("/{storyboard_id}")
    def detail(
        storyboard_id: UUID,
        scope: Read,
        connection: Database,
        revision: Annotated[int | None, Query(ge=1, le=MAX_REVISIONS)] = None,
    ) -> Studio:
        return load_studio(connection, scope | {"storyboard": storyboard_id}, revision)

    @router.post("", status_code=201)
    def generate(
        scope: Write, connection: Database, data: Annotated[Generate, Depends(generate_body)]
    ) -> Storyboard:
        workspace_lock(connection, scope["workspace"])
        release_record(connection, scope["workspace"], data.release_id)
        count = connection.execute(
            text(f"SELECT count(*) FROM demoforge.storyboards WHERE {OPPORTUNITY}"), scope
        ).scalar_one()
        if count >= MAX_STORYBOARDS:
            raise HTTPException(409, "This opportunity has reached its storyboard limit.")
        inputs = eligible_inputs(connection, scope | {"release": data.release_id})
        brief = Brief.model_validate(data.model_dump(exclude={"release_id"}))
        if len(inputs) > brief.target_minutes:
            raise HTTPException(422, "Allow at least one minute per approved requirement.")
        scenes = StoryboardPlanner().plan(brief, inputs)
        scope = scope | {"storyboard": uuid4()}
        connection.execute(
            text("""
            INSERT INTO demoforge.storyboards
                (workspace_id, opportunity_id, release_id, id, audience, target_minutes,
                 business_outcomes)
            VALUES (:workspace, :opportunity, :release, :storyboard, :audience,
                    :target_minutes, :business_outcomes)
        """),
            scope | brief.model_dump() | {"release": data.release_id},
        )
        return append_revision(connection, scope, data.release_id, scenes, "generated", 1)

    @router.put("/{storyboard_id}/scenes/{scene_id}")
    def edit(
        storyboard_id: UUID,
        scene_id: UUID,
        scope: Write,
        connection: Database,
        data: Annotated[SceneEdit, Depends(edit_body)],
    ) -> Storyboard:
        scope = scope | {"storyboard": storyboard_id}
        board = load_base(connection, scope, data.revision)
        scene = find_scene(board, scene_id)
        content = SceneCopy.model_validate(data.model_dump(exclude={"revision"}))
        fields = [
            field
            for field in FIELDS
            if field in scene.edited_fields
            or getattr(content, field) != getattr(scene.content, field)
        ]
        if content == scene.content:
            return board
        updated = scene.model_copy(update={"content": content, "edited_fields": fields})
        return save(connection, scope, board, replacing(board, updated), "scene_edited")

    @router.put("/{storyboard_id}/agenda")
    def agenda(
        storyboard_id: UUID,
        scope: Write,
        connection: Database,
        data: Annotated[AgendaEdit, Depends(agenda_body)],
    ) -> Storyboard:
        scope = scope | {"storyboard": storyboard_id}
        board = load_base(connection, scope, data.revision)
        current = {scene.id: scene for scene in board.scenes}
        if len(data.scenes) != len(current) or {slot.id for slot in data.scenes} != current.keys():
            raise HTTPException(422, "The agenda must contain each current scene exactly once.")
        if sum(slot.minutes for slot in data.scenes) != board.brief.target_minutes:
            raise HTTPException(422, "Scene time must sum to the target duration.")
        scenes = [
            current[slot.id].model_copy(update={"minutes": slot.minutes}) for slot in data.scenes
        ]
        if scenes == board.scenes:
            return board
        return save(connection, scope, board, scenes, "agenda_updated")

    @router.post("/{storyboard_id}/scenes/{scene_id}/proposal")
    def propose(
        storyboard_id: UUID,
        scene_id: UUID,
        scope: Write,
        connection: Database,
        data: Annotated[Approval, Depends(revision_body)],
    ) -> Proposal:
        scope = scope | {"storyboard": storyboard_id}
        board = load_base(connection, scope, data.revision)
        return preview(connection, scope, board, find_scene(board, scene_id))

    @router.post("/{storyboard_id}/scenes/{scene_id}/apply")
    def apply(
        storyboard_id: UUID,
        scene_id: UUID,
        scope: Write,
        connection: Database,
        data: Annotated[ProposalAcceptance, Depends(apply_body)],
    ) -> Storyboard:
        scope = scope | {"storyboard": storyboard_id}
        board = load_base(connection, scope, data.revision)
        existing = find_scene(board, scene_id)
        candidate = preview(connection, scope, board, existing)
        if candidate.fingerprint != data.fingerprint:
            raise HTTPException(
                409, "The evidence changed. Preview the proposal again before applying it."
            )
        scene = candidate.scene
        if existing.edited_fields and not data.replace_edits:
            content = scene.content.model_copy(
                update={key: getattr(existing.content, key) for key in existing.edited_fields}
            )
            scene = scene.model_copy(
                update={"content": content, "edited_fields": existing.edited_fields}
            )
        if scene == existing:
            return board
        return save(connection, scope, board, replacing(board, scene), "scene_regenerated")

    @router.post("/{storyboard_id}/approve")
    def approve(
        storyboard_id: UUID,
        scope: Write,
        connection: Database,
        data: Annotated[StoryboardApproval, Depends(approval_body)],
    ) -> Storyboard:
        scope = scope | {"storyboard": storyboard_id}
        board = load_base(connection, scope, data.revision)
        if any(scene.stale_evidence for scene in board.scenes):
            raise HTTPException(
                409, "Refresh scenes with stale requirements or mappings before approval."
            )
        if not data.acknowledge_warnings and any(scene.support_warning for scene in board.scenes):
            raise HTTPException(422, "Acknowledge the product support warnings before approval.")
        connection.execute(
            text("""
            INSERT INTO demoforge.storyboard_approvals
                (workspace_id, opportunity_id, storyboard_id, revision, warnings_acknowledged)
            VALUES (:workspace, :opportunity, :storyboard, :revision, :warnings_acknowledged)
            ON CONFLICT DO NOTHING
        """),
            scope | {"revision": data.revision, "warnings_acknowledged": data.acknowledge_warnings},
        )
        return load_studio(connection, scope, data.revision).storyboard

    return router
