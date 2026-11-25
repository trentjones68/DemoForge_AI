"""Match approved statements to exact phrases published in the catalog."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

SupportStatus = Literal["supported", "partial", "unsupported", "unknown"]


def match_key(statement: str) -> str:
    return " ".join(statement.casefold().split()).rstrip(".?!").rstrip()


class CatalogEvidence(Protocol):
    id: UUID
    revision: int
    support_status: SupportStatus
    match_phrases: list[str]


@dataclass(frozen=True)
class Match:
    support_status: SupportStatus
    rationale: str
    capability_id: UUID | None = None
    capability_revision: int | None = None


class CapabilityMatcher:
    def __init__(self, evidence: Sequence[CatalogEvidence]) -> None:
        self.phrases: dict[str, list[CatalogEvidence]] = {}
        for capability in evidence:
            for key in {match_key(phrase) for phrase in capability.match_phrases} - {""}:
                self.phrases.setdefault(key, []).append(capability)

    def match(self, statement: str) -> Match:
        candidates = self.phrases.get(match_key(statement), [])
        if not candidates:
            return Match("unknown", "No current catalog entry covers this exact requirement.")
        if len(candidates) > 1:
            return Match(
                "unknown", "Multiple catalog entries match. Review the available evidence."
            )
        capability = candidates[0]
        return Match(
            capability.support_status,
            "Exact catalog phrase match. Verify the source, limitations, and dependencies.",
            capability.id,
            capability.revision,
        )
