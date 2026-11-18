from collections.abc import Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class JobMessageV1(BaseModel):
    """Pointer to a persisted job. Tenant context comes from the job record."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    job_id: UUID

    @field_validator("schema_version", mode="before")
    @classmethod
    def reject_boolean_version(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("schema_version must be an integer")
        return value


JobHandler = Callable[[JobMessageV1], None]


class DurableJobQueue(Protocol):
    def publish(self, message: JobMessageV1) -> None:
        """Return only after the broker durably accepts the message."""
        ...

    def consume(self, handler: JobHandler) -> None:
        """Acknowledge after successful handling. The backend owns redelivery."""
        ...
