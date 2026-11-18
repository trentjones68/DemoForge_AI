from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import Connection, Engine, text

from demoforge_api.auth import TokenVerifier
from demoforge_api.request_access import access_dependencies


class Role(StrEnum):
    ADMIN = "admin"
    PRODUCT_ADMIN = "product_admin"
    SALES_ENGINEER = "sales_engineer"
    VIEWER = "viewer"


class WorkspaceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Workspace(BaseModel):
    id: UUID
    name: str
    role: Role


class MemberWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["product_admin", "sales_engineer", "viewer"]


class Member(BaseModel):
    user_id: UUID
    role: Role


def find_workspace(connection: Connection, workspace_id: UUID, actor: UUID) -> Workspace:
    row = (
        connection.execute(
            text("""
            SELECT w.id, w.name, m.role
            FROM demoforge.workspaces w
            JOIN demoforge.memberships m ON m.workspace_id = w.id
            WHERE w.id = :workspace_id AND m.user_id = :actor
        """),
            {"workspace_id": workspace_id, "actor": actor},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Workspace not found")
    return Workspace.model_validate(row)


def workspace_router(engine: Engine | None, verifier: TokenVerifier) -> APIRouter:
    router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])
    authenticate, transaction = access_dependencies(engine, verifier)
    Actor = Annotated[UUID, Depends(authenticate)]
    Database = Annotated[Connection, Depends(transaction, scope="function")]

    def require_admin(connection: Connection, workspace_id: UUID, actor: UUID) -> None:
        if find_workspace(connection, workspace_id, actor).role != Role.ADMIN:
            raise HTTPException(403, "Workspace admin required")

    @router.get("")
    def list_workspaces(connection: Database, actor: Actor) -> list[Workspace]:
        rows = connection.execute(
            text("""
                SELECT w.id, w.name, m.role
                FROM demoforge.workspaces w
                JOIN demoforge.memberships m ON m.workspace_id = w.id
                WHERE m.user_id = :actor ORDER BY w.name, w.id
            """),
            {"actor": actor},
        ).mappings()
        return [Workspace.model_validate(row) for row in rows]

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_workspace(data: WorkspaceWrite, connection: Database, actor: Actor) -> Workspace:
        workspace_id = connection.execute(
            text("SELECT demoforge.create_workspace(:name)"), {"name": data.name}
        ).scalar_one()
        return find_workspace(connection, workspace_id, actor)

    @router.get("/{workspace_id}")
    def get_workspace(workspace_id: UUID, connection: Database, actor: Actor) -> Workspace:
        return find_workspace(connection, workspace_id, actor)

    @router.patch("/{workspace_id}")
    def rename_workspace(
        workspace_id: UUID, data: WorkspaceWrite, connection: Database, actor: Actor
    ) -> Workspace:
        require_admin(connection, workspace_id, actor)
        row = connection.execute(
            text(
                "UPDATE demoforge.workspaces SET name = :name WHERE id = :workspace_id RETURNING id"
            ),
            {"name": data.name, "workspace_id": workspace_id},
        ).one_or_none()
        if row is None:
            raise HTTPException(403, "Workspace admin required")
        return find_workspace(connection, workspace_id, actor)

    @router.get("/{workspace_id}/members")
    def list_members(workspace_id: UUID, connection: Database, actor: Actor) -> list[Member]:
        require_admin(connection, workspace_id, actor)
        rows = connection.execute(
            text("""
                SELECT user_id, role FROM demoforge.memberships
                WHERE workspace_id = :workspace_id ORDER BY user_id
            """),
            {"workspace_id": workspace_id},
        ).mappings()
        return [Member.model_validate(row) for row in rows]

    @router.put("/{workspace_id}/members/{user_id}")
    def upsert_member(
        workspace_id: UUID, user_id: UUID, data: MemberWrite, connection: Database, actor: Actor
    ) -> Member:
        require_admin(connection, workspace_id, actor)
        row = (
            connection.execute(
                text("""
                INSERT INTO demoforge.memberships (workspace_id, user_id, role)
                VALUES (:workspace_id, :user_id, :role)
                ON CONFLICT (workspace_id, user_id)
                DO UPDATE SET role = excluded.role WHERE memberships.role <> 'admin'
                RETURNING user_id, role
            """),
                {"workspace_id": workspace_id, "user_id": user_id, "role": data.role},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(403, "Admin membership cannot be changed here")
        return Member.model_validate(row)

    @router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_member(
        workspace_id: UUID, user_id: UUID, connection: Database, actor: Actor
    ) -> Response:
        require_admin(connection, workspace_id, actor)
        row = connection.execute(
            text("""
                DELETE FROM demoforge.memberships
                WHERE workspace_id = :workspace_id AND user_id = :user_id
                RETURNING user_id
            """),
            {"workspace_id": workspace_id, "user_id": user_id},
        ).one_or_none()
        if row is None:
            raise HTTPException(404, "Removable membership not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
