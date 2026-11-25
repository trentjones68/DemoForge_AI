"""Catalog administration and opportunity-scoped review."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text

from demoforge_api.analysis.routes import Approval
from demoforge_api.analysis.schema import StrictModel
from demoforge_api.auth import TokenVerifier
from demoforge_api.catalog.matcher import CapabilityMatcher, Match, match_key
from demoforge_api.catalog.models import (
    Capability,
    CapabilityEdit,
    CapabilityInput,
    CapabilityPage,
    Generated,
    Mapping,
    MappingBoard,
    MappingEdit,
    Release,
    ReleaseInput,
)
from demoforge_api.discovery.routes import opportunity_access, read_body, workspace_lock
from demoforge_api.planning.models import ApprovedRequirement
from demoforge_api.request_access import access_dependencies
from demoforge_api.workspaces import Role, find_workspace

MAX_ENTRIES = 200
MAX_RELEASES = 100
MAX_REQUIREMENTS = 200
PAGE_SIZE = 30
CATALOG = "/{workspace_id}/catalog/releases"
MAPPINGS = "/{workspace_id}/opportunities/{opportunity_id}/capability-mappings/{release_id}"
CAPABILITY_SCOPE = "workspace_id = :workspace AND release_id = :release"

MAPPING_COLUMNS = "m.*, CASE WHEN c.id IS NOT NULL THEN to_jsonb(c) END AS capability"
MAPPING_EVIDENCE = """
    LEFT JOIN demoforge.catalog_capabilities c
      ON (c.workspace_id, c.release_id, c.id, c.revision) =
         (m.workspace_id, m.release_id, m.capability_id, m.capability_revision)
    WHERE m.workspace_id = :workspace AND m.opportunity_id = :opportunity
      AND m.release_id = :release
"""


def authorize_catalog(connection: Connection, workspace: UUID, actor: UUID, write: bool) -> None:
    role = find_workspace(connection, workspace, actor).role
    if role in (Role.ADMIN, Role.PRODUCT_ADMIN) or (role == Role.SALES_ENGINEER and not write):
        return
    raise HTTPException(403, "Catalog access denied.")


def release_record(connection: Connection, workspace: UUID, release: UUID) -> Release:
    row = (
        connection.execute(
            text("""
        SELECT * FROM demoforge.catalog_releases WHERE workspace_id = :workspace AND id = :release
    """),
            {"workspace": workspace, "release": release},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Catalog release not found.")
    return Release.model_validate(row)


def capability_record(connection: Connection, params: dict[str, UUID], item: UUID) -> Capability:
    row = (
        connection.execute(
            text(f"""
        SELECT * FROM demoforge.current_catalog_capabilities WHERE {CAPABILITY_SCOPE} AND id = :id
    """),
            params | {"id": item},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Catalog capability not found.")
    return Capability.model_validate(row)


def add_capability_revision(
    connection: Connection,
    params: dict[str, UUID],
    item: UUID,
    version: int,
    fields: CapabilityInput,
    archived: bool = False,
) -> Capability:
    row = (
        connection.execute(
            text("""
        INSERT INTO demoforge.catalog_capabilities (
            workspace_id, release_id, id, revision, name, description, support_status,
            limitations, dependencies, match_phrases, source_title, source_url, source_locator,
            archived
        ) VALUES (
            :workspace, :release, :id, :revision, :name, :description, :support_status,
            :limitations, :dependencies, :match_phrases, :source_title, :source_url,
            :source_locator, :archived
        )
        RETURNING *
    """),
            fields.model_dump()
            | params
            | {
                "id": item,
                "revision": version,
                "archived": archived,
            },
        )
        .mappings()
        .one()
    )
    return Capability.model_validate(row)


def active_capabilities(connection: Connection, params: dict[str, UUID]) -> list[Capability]:
    rows = connection.execute(
        text(f"""
        SELECT * FROM demoforge.current_catalog_capabilities WHERE {CAPABILITY_SCOPE}
          AND NOT archived ORDER BY lower(name), id
    """),
        params,
    ).mappings()
    return [Capability.model_validate(row) for row in rows]


def draft_requirements(
    connection: Connection, params: dict[str, UUID]
) -> list[ApprovedRequirement]:
    rows = (
        connection.execute(
            text("""
        SELECT * FROM demoforge.approved_storyboard_requirements
        WHERE workspace_id = :workspace AND opportunity_id = :opportunity
        ORDER BY session_id, id LIMIT :limit
    """),
            params | {"limit": MAX_REQUIREMENTS + 1},
        )
        .mappings()
        .all()
    )
    if len(rows) > MAX_REQUIREMENTS:
        raise HTTPException(409, "This opportunity exceeds the approved requirement limit.")
    return [ApprovedRequirement.model_validate(row) for row in rows]


def mappings(
    connection: Connection,
    params: dict[str, UUID],
    reviewed: bool = False,
) -> list[Mapping]:
    view = "reviewed_storyboard_mappings" if reviewed else "current_capability_mappings"
    rows = connection.execute(
        text(f"SELECT {MAPPING_COLUMNS} FROM demoforge.{view} m {MAPPING_EVIDENCE} ORDER BY m.id"),
        params,
    ).mappings()
    return [Mapping.model_validate(row) for row in rows]


def mapping_record(connection: Connection, params: dict[str, UUID], mapping_id: UUID) -> Mapping:
    row = (
        connection.execute(
            text(f"""
        SELECT {MAPPING_COLUMNS} FROM demoforge.current_capability_mappings m
        {MAPPING_EVIDENCE} AND m.id = :id
    """),
            params | {"id": mapping_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Mapping or approved requirement not found.")
    return Mapping.model_validate(row)


def mapping_evidence(match: Match) -> dict[str, object]:
    return {
        "status": match.support_status,
        "rationale": match.rationale,
        "capability_id": match.capability_id,
        "capability_revision": match.capability_revision,
    }


INSERT_MAPPING_REVISION = """
    INSERT INTO demoforge.mapping_revisions (
        workspace_id, opportunity_id, release_id, mapping_id, revision,
        capability_id, capability_revision, support_status, rationale
    ) VALUES (
        :workspace, :opportunity, :release, :id, :revision,
        :capability_id, :capability_revision, :status, :rationale
    )
"""


def generate_mappings(connection: Connection, params: dict[str, UUID]) -> Generated:
    approved = draft_requirements(connection, params)
    if not approved:
        raise HTTPException(409, "Approve a requirement before generating mappings.")
    existing = set(
        connection.execute(
            text("""
        SELECT session_id, requirement_id, requirement_revision
        FROM demoforge.capability_mappings
        WHERE workspace_id = :workspace AND opportunity_id = :opportunity AND release_id = :release
    """),
            params,
        ).tuples()
    )
    missing = [r for r in approved if (r.session_id, r.id, r.revision) not in existing]
    if not missing:
        return Generated(added=0)
    matcher = CapabilityMatcher(active_capabilities(connection, params))
    rows = [
        params
        | {
            "id": uuid4(),
            "session": r.session_id,
            "requirement": r.id,
            "requirement_revision": r.revision,
            "revision": 1,
        }
        | mapping_evidence(matcher.match(r.statement))
        for r in missing
    ]

    connection.execute(
        text("""
        INSERT INTO demoforge.capability_mappings (
            workspace_id, opportunity_id, release_id, id, session_id,
            requirement_id, requirement_revision
        ) VALUES (
            :workspace, :opportunity, :release, :id, :session, :requirement, :requirement_revision
        )
    """),
        rows,
    )
    connection.execute(text(INSERT_MAPPING_REVISION), rows)
    return Generated(added=len(rows))


async def catalog_body[Model: StrictModel](request: Request, model: type[Model]) -> Model:
    raw = await read_body(request, 65_536)
    if b"\\u0000" in raw.lower():
        raise HTTPException(422, "Use plain text for catalog and review fields.")
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(
            422, "Check the revision, required fields, HTTPS source, and support limitations."
        ) from None


def catalog_router(engine: Engine | None, verifier: TokenVerifier) -> APIRouter:
    router = APIRouter(prefix="/v1/workspaces", tags=["catalog"])
    authenticate, database = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(database, scope="function")]

    async def release_body(request: Request, _: Actor) -> ReleaseInput:
        return await catalog_body(request, ReleaseInput)

    async def new_body(request: Request, _: Actor) -> CapabilityInput:
        return await catalog_body(request, CapabilityInput)

    async def edit_body(request: Request, _: Actor) -> CapabilityEdit:
        return await catalog_body(request, CapabilityEdit)

    async def revision_body(request: Request, _: Actor) -> Approval:
        return await catalog_body(request, Approval)

    async def mapping_body(request: Request, _: Actor) -> MappingEdit:
        return await catalog_body(request, MappingEdit)

    @router.get(CATALOG)
    def list_releases(workspace_id: UUID, actor: Actor, connection: Database) -> list[Release]:
        authorize_catalog(connection, workspace_id, actor, write=False)
        rows = connection.execute(
            text("""
            SELECT * FROM demoforge.catalog_releases WHERE workspace_id = :workspace
            ORDER BY lower(product), created_at DESC, id
        """),
            {"workspace": workspace_id},
        ).mappings()
        return [Release.model_validate(row) for row in rows]

    @router.post(CATALOG, status_code=201)
    def create_release(
        workspace_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[ReleaseInput, Depends(release_body)],
    ) -> Release:
        authorize_catalog(connection, workspace_id, actor, write=True)
        workspace_lock(connection, workspace_id)
        count = connection.execute(
            text("""
            SELECT count(*) FROM demoforge.catalog_releases WHERE workspace_id = :workspace
        """),
            {"workspace": workspace_id},
        ).scalar_one()
        if count >= MAX_RELEASES:
            raise HTTPException(409, "This workspace has reached its catalog release limit.")
        row = (
            connection.execute(
                text("""
            INSERT INTO demoforge.catalog_releases (workspace_id, id, product, version)
            VALUES (:workspace, :id, :product, :version) ON CONFLICT DO NOTHING RETURNING *
        """),
                data.model_dump() | {"workspace": workspace_id, "id": uuid4()},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(409, "This product version already exists.")
        return Release.model_validate(row)

    capabilities = CATALOG + "/{release_id}/capabilities"

    def catalog_scope(
        connection: Connection,
        workspace: UUID,
        release: UUID,
        actor: UUID,
        write: bool,
    ) -> dict[str, UUID]:
        authorize_catalog(connection, workspace, actor, write=write)
        if write:
            workspace_lock(connection, workspace)
        release_record(connection, workspace, release)
        return {"workspace": workspace, "release": release}

    @router.get(capabilities)
    def search(
        workspace_id: UUID,
        release_id: UUID,
        actor: Actor,
        connection: Database,
        q: Annotated[str, Query(max_length=120, pattern=r"^[^\x00]*$")] = "",
        page: Annotated[int, Query(ge=1, le=7)] = 1,
        include_archived: bool = False,
    ) -> CapabilityPage:
        params = catalog_scope(connection, workspace_id, release_id, actor, write=False)
        rows = (
            connection.execute(
                text(f"""
            SELECT * FROM demoforge.current_catalog_capabilities WHERE {CAPABILITY_SCOPE}
              AND (:include_archived OR NOT archived)
              AND strpos(lower(concat_ws(' ', name, description, limitations,
                                          array_to_string(dependencies, ' '), source_title,
                                          source_locator, source_url,
                                          array_to_string(match_phrases, ' '))), lower(:q)) > 0
            ORDER BY archived, lower(name), id LIMIT :limit OFFSET :offset
        """),
                params
                | {
                    "include_archived": include_archived,
                    "q": q.strip(),
                    "limit": PAGE_SIZE + 1,
                    "offset": (page - 1) * PAGE_SIZE,
                },
            )
            .mappings()
            .all()
        )
        return CapabilityPage(
            entries=[Capability.model_validate(row) for row in rows[:PAGE_SIZE]],
            more=len(rows) > PAGE_SIZE,
        )

    @router.get(capabilities + "/{item_id}")
    def detail(
        workspace_id: UUID,
        release_id: UUID,
        item_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> Capability:
        params = catalog_scope(connection, workspace_id, release_id, actor, write=False)
        return capability_record(connection, params, item_id)

    @router.post(capabilities, status_code=201)
    def create(
        workspace_id: UUID,
        release_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[CapabilityInput, Depends(new_body)],
    ) -> Capability:
        params = catalog_scope(connection, workspace_id, release_id, actor, write=True)
        count = connection.execute(
            text(f"""
            SELECT count(*) FROM demoforge.current_catalog_capabilities WHERE {CAPABILITY_SCOPE}
        """),
            params,
        ).scalar_one()
        if count >= MAX_ENTRIES:
            raise HTTPException(409, "This release has reached its capability limit.")
        return add_capability_revision(connection, params, uuid4(), 1, data)

    @router.put(capabilities + "/{item_id}")
    def revise(
        workspace_id: UUID,
        release_id: UUID,
        item_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[CapabilityEdit, Depends(edit_body)],
    ) -> Capability:
        params = catalog_scope(connection, workspace_id, release_id, actor, write=True)
        current = capability_record(connection, params, item_id)
        if current.revision != data.revision or current.archived:
            raise HTTPException(409, "The capability changed or was archived. Refresh to continue.")
        return add_capability_revision(connection, params, item_id, current.revision + 1, data)

    @router.post(capabilities + "/{item_id}/archive")
    def archive(
        workspace_id: UUID,
        release_id: UUID,
        item_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[Approval, Depends(revision_body)],
    ) -> Capability:
        params = catalog_scope(connection, workspace_id, release_id, actor, write=True)
        current = capability_record(connection, params, item_id)
        if current.revision != data.revision or current.archived:
            raise HTTPException(409, "The capability changed or was archived. Refresh to continue.")
        return add_capability_revision(
            connection, params, item_id, current.revision + 1, current, archived=True
        )

    def mapping_scope(
        connection: Connection,
        workspace: UUID,
        opportunity: UUID,
        release: UUID,
        actor: UUID,
        write: bool,
    ) -> tuple[dict[str, UUID], Release]:
        opportunity_access(connection, workspace, opportunity, actor, write=write)
        if write:
            workspace_lock(connection, workspace)
        params = {"workspace": workspace, "opportunity": opportunity, "release": release}
        return params, release_record(connection, workspace, release)

    @router.get(MAPPINGS)
    def board(
        workspace_id: UUID,
        opportunity_id: UUID,
        release_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> MappingBoard:
        params, release = mapping_scope(
            connection, workspace_id, opportunity_id, release_id, actor, write=False
        )
        return MappingBoard(
            release=release,
            requirements=draft_requirements(connection, params),
            mappings=mappings(connection, params),
            capabilities=active_capabilities(connection, params),
        )

    @router.post(MAPPINGS + "/generate")
    def generate(
        workspace_id: UUID,
        opportunity_id: UUID,
        release_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> Generated:
        params, _ = mapping_scope(
            connection, workspace_id, opportunity_id, release_id, actor, write=True
        )
        return generate_mappings(connection, params)

    @router.put(MAPPINGS + "/items/{mapping_id}")
    def edit_mapping(
        workspace_id: UUID,
        opportunity_id: UUID,
        release_id: UUID,
        mapping_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[MappingEdit, Depends(mapping_body)],
    ) -> Mapping:
        params, _ = mapping_scope(
            connection, workspace_id, opportunity_id, release_id, actor, write=True
        )
        current = mapping_record(connection, params, mapping_id)
        if current.revision != data.revision:
            raise HTTPException(
                409, "The mapping changed. Refresh and review the current revision."
            )
        evidence = (
            capability_record(connection, params, data.capability_id)
            if data.capability_id is not None
            else None
        )
        if evidence is not None and (
            evidence.archived or evidence.revision != data.capability_revision
        ):
            raise HTTPException(409, "The selected catalog revision is no longer current.")
        if evidence is not None and match_key(current.requirement_statement) not in {
            match_key(phrase) for phrase in evidence.match_phrases
        }:
            raise HTTPException(
                422, "The selected evidence lacks an exact phrase for this requirement."
            )
        match = Match(
            evidence.support_status if evidence else "unknown",
            data.rationale,
            data.capability_id,
            data.capability_revision,
        )
        connection.execute(
            text(INSERT_MAPPING_REVISION),
            params
            | {
                "id": mapping_id,
                "revision": current.revision + 1,
            }
            | mapping_evidence(match),
        )
        return mapping_record(connection, params, mapping_id)

    @router.post(MAPPINGS + "/items/{mapping_id}/review")
    def review(
        workspace_id: UUID,
        opportunity_id: UUID,
        release_id: UUID,
        mapping_id: UUID,
        actor: Actor,
        connection: Database,
        data: Annotated[Approval, Depends(revision_body)],
    ) -> Mapping:
        params, _ = mapping_scope(
            connection, workspace_id, opportunity_id, release_id, actor, write=True
        )
        current = mapping_record(connection, params, mapping_id)
        if current.revision != data.revision or current.stale_evidence:
            raise HTTPException(
                409, "The mapping or catalog evidence changed. Review a fresh revision."
            )
        connection.execute(
            text("""
            INSERT INTO demoforge.mapping_reviews
                (workspace_id, opportunity_id, release_id, mapping_id, revision)
            VALUES (:workspace, :opportunity, :release, :id, :revision) ON CONFLICT DO NOTHING
        """),
            params | {"id": mapping_id, "revision": current.revision},
        )
        return mapping_record(connection, params, mapping_id)

    @router.get(MAPPINGS + "/reviewed")
    def reviewed_inputs(
        workspace_id: UUID,
        opportunity_id: UUID,
        release_id: UUID,
        actor: Actor,
        connection: Database,
    ) -> list[Mapping]:
        params, _ = mapping_scope(
            connection, workspace_id, opportunity_id, release_id, actor, write=False
        )
        return mappings(connection, params, reviewed=True)

    return router
