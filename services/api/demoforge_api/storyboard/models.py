"""Typed storyboard inputs, scene content, and immutable revision responses."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from demoforge_api.analysis.routes import Revision
from demoforge_api.analysis.schema import StrictModel
from demoforge_api.catalog.matcher import SupportStatus
from demoforge_api.planning.normalizer import Priority

MAX_SCENES = 40
MAX_STORYBOARDS = 25
MAX_REVISIONS = 250
Note = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2400, pattern=r"^[^\x00]*$"),
]
Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\x00]*$"),
]
Notes = Annotated[list[Note], Field(max_length=6)]
Minutes = Annotated[int, Field(ge=1, le=180)]
EditField = Literal["title", "actions", "talk_track", "expected_outcome", "synthetic_data", "risks"]
RevisionAction = Literal["generated", "scene_edited", "agenda_updated", "scene_regenerated"]


class Brief(StrictModel):
    audience: Label
    target_minutes: Minutes
    business_outcomes: Annotated[list[Label], Field(min_length=1, max_length=5)]


class Generate(Brief):
    release_id: UUID


class SceneCopy(StrictModel):
    title: Label
    actions: Annotated[list[Note], Field(min_length=1, max_length=6)]
    talk_track: Note
    expected_outcome: Note
    synthetic_data: Notes
    risks: Notes


class SceneEdit(SceneCopy):
    revision: Revision


class Slot(StrictModel):
    id: UUID
    minutes: Minutes


class AgendaEdit(StrictModel):
    revision: Revision
    scenes: Annotated[list[Slot], Field(min_length=1, max_length=MAX_SCENES)]


class ProposalAcceptance(StrictModel):
    revision: Revision
    fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    replace_edits: bool = False


class StoryboardApproval(StrictModel):
    revision: Revision
    acknowledge_warnings: bool = False


class Gap(StrictModel):
    id: UUID
    revision: int
    question: str
    priority: Priority
    status: Literal["open", "in_progress"]


class CatalogRef(StrictModel):
    id: UUID
    revision: int
    name: str
    source_title: str
    source_url: str
    source_locator: str
    limitations: str
    dependencies: list[str]


class Evidence(StrictModel):
    session_id: UUID
    requirement_id: UUID
    requirement_revision: int
    requirement: str
    priority: Priority
    mapping_id: UUID
    mapping_revision: int
    support_status: SupportStatus
    mapping_rationale: str
    capability: CatalogRef | None

    @model_validator(mode="after")
    def requires_catalog_ref(self) -> Self:
        if self.support_status != "unknown" and self.capability is None:
            raise ValueError("A product support classification requires a catalog reference")
        return self


class Scene(StrictModel):
    id: UUID
    minutes: Minutes
    content: SceneCopy
    evidence: Evidence
    gaps: list[Gap]
    edited_fields: list[EditField]
    stale_evidence: bool
    support_warning: str | None

    @model_validator(mode="after")
    def validate_support_warning(self) -> Self:
        if self.evidence.support_status != "supported" and not self.support_warning:
            raise ValueError("A scene with limited or unverified support requires a warning")
        return self


class ReleaseRef(StrictModel):
    id: UUID
    product: str
    version: str


class RevisionSummary(StrictModel):
    revision: int
    action: RevisionAction
    actor_id: UUID
    created_at: datetime
    approved_by: UUID | None
    approved_at: datetime | None


class Storyboard(RevisionSummary):
    schema_version: Literal[1] = 1
    id: UUID
    release: ReleaseRef
    brief: Brief
    scenes: Annotated[list[Scene], Field(min_length=1, max_length=MAX_SCENES)]

    @model_validator(mode="after")
    def validate_agenda(self) -> Self:
        if sum(scene.minutes for scene in self.scenes) != self.brief.target_minutes:
            raise ValueError("Scene time must sum to the demo duration")
        if len({scene.id for scene in self.scenes}) != len(self.scenes):
            raise ValueError("Scene identifiers must be unique")
        return self


class StoryboardSummary(StrictModel):
    id: UUID
    audience: str
    release: ReleaseRef
    revision: int


class Studio(StrictModel):
    current_revision: int
    revisions: list[RevisionSummary]
    storyboard: Storyboard


class Proposal(StrictModel):
    scene: Scene
    fingerprint: str
