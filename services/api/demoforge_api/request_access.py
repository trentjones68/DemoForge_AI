from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, Engine

from demoforge_api.auth import TokenVerifier
from demoforge_api.db import DatabaseIdentityError, workspace_transaction


def access_dependencies(
    engine: Engine | None, verifier: TokenVerifier
) -> tuple[
    Callable[[HTTPAuthorizationCredentials | None], UUID],
    Callable[[UUID], Iterator[Connection]],
]:
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> UUID:
        if credentials is None:
            raise HTTPException(401, "Sign-in required", headers={"WWW-Authenticate": "Bearer"})
        return verifier.subject(credentials.credentials)

    def transaction(actor: Annotated[UUID, Depends(authenticate)]) -> Iterator[Connection]:
        with actor_transaction(engine, actor) as connection:
            yield connection

    return authenticate, transaction


@contextmanager
def actor_transaction(engine: Engine | None, actor: UUID) -> Iterator[Connection]:
    if engine is None:
        raise HTTPException(503, "Workspace service unavailable")
    try:
        with workspace_transaction(engine, actor) as connection:
            yield connection
    except DatabaseIdentityError:
        raise HTTPException(503, "Workspace service unavailable") from None
