"""Readiness policy for one pinned storyboard revision."""

from collections.abc import Collection, Mapping
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

from demoforge_api.analysis.routes import Revision
from demoforge_api.analysis.schema import StrictModel
from demoforge_api.opportunities import Opportunity
from demoforge_api.storyboard.models import Studio
from demoforge_api.storyboard.store import Scope

PrepTask = Literal["synthetic_data", "rehearsal", "risk_review"]
RequirementKey = tuple[UUID, UUID, int]
PREP_TASKS: dict[PrepTask, str] = {
    "synthetic_data": "Prepare and verify fictional demo data",
    "rehearsal": "Rehearse the flow and verify the demo environment and integrations",
    "risk_review": "Review demo risks and agree on a fallback",
}


class PrepUpdate(StrictModel):
    revision: Revision
    complete: bool


class Check(StrictModel):
    label: str
    complete: bool
    blocker: str | None = None
    task: PrepTask | None = None


class Readiness(StrictModel):
    revision: int
    ready: bool
    checks: list[Check]


def automatic(label: str, blocker: str, *, complete: bool) -> Check:
    return Check(label=label, complete=complete, blocker=None if complete else blocker)


def assess(
    studio: Studio,
    current_requirements: Collection[RequirementKey],
    unresolved_gaps: int,
    preparations: Mapping[PrepTask, bool],
    *,
    archived: bool = False,
) -> Readiness:
    board = studio.storyboard
    pinned = {
        (
            scene.evidence.session_id,
            scene.evidence.requirement_id,
            scene.evidence.requirement_revision,
        )
        for scene in board.scenes
    }
    stale_positions = [str(i) for i, scene in enumerate(board.scenes, 1) if scene.stale_evidence]
    limited = [
        f"{i} ({scene.evidence.support_status})"
        for i, scene in enumerate(board.scenes, 1)
        if scene.evidence.support_status != "supported"
    ]
    checks = [
        automatic(
            "Approve this revision",
            "This storyboard revision needs approval.",
            complete=board.approved_at is not None,
        ),
        automatic(
            "Use the current storyboard",
            "Select the latest storyboard revision.",
            complete=board.revision == studio.current_revision,
        ),
        automatic(
            "Plan an active opportunity", "The opportunity is archived.", complete=not archived
        ),
        automatic(
            "Cover all currently approved requirements",
            "The approved requirements changed. Refresh scenes or generate a new storyboard.",
            complete=pinned == set(current_requirements),
        ),
        automatic(
            "Verify current requirement and catalog evidence",
            f"Refresh stale evidence for scenes {', '.join(stale_positions)}.",
            complete=not stale_positions,
        ),
        automatic(
            "Verify full product support for each scene",
            f"Full product support is missing for scenes {', '.join(limited)}.",
            complete=not limited,
        ),
        automatic(
            "Resolve linked discovery questions",
            f"Resolve or approve the resolution of {unresolved_gaps} linked discovery questions.",
            complete=unresolved_gaps == 0,
        ),
    ]
    for task, label in PREP_TASKS.items():
        complete = preparations.get(task, False)
        checks.append(
            Check(
                task=task,
                label=label,
                complete=complete,
                blocker=None if complete else f"Complete demo prep and confirm: {label.lower()}.",
            )
        )
    return Readiness(
        revision=board.revision, ready=all(check.complete for check in checks), checks=checks
    )


def preparation_states(connection: Connection, scope: Scope, revision: int) -> dict[PrepTask, bool]:
    rows = connection.execute(
        text("""
        SELECT DISTINCT ON (task) task, complete FROM demoforge.storyboard_prep_events
        WHERE workspace_id = :workspace AND opportunity_id = :opportunity
          AND storyboard_id = :storyboard AND revision = :revision
        ORDER BY task, id DESC
    """),
        scope | {"revision": revision},
    ).tuples()
    return {task: complete for task, complete in rows}


def readiness_for(
    connection: Connection, scope: Scope, studio: Studio, opportunity: Opportunity
) -> Readiness:
    rows = connection.execute(
        text("""
        SELECT session_id, id, revision FROM demoforge.approved_storyboard_requirements
        WHERE workspace_id = :workspace AND opportunity_id = :opportunity
    """),
        scope,
    ).tuples()
    current: set[RequirementKey] = {(session, item, revision) for session, item, revision in rows}
    unresolved: int = connection.execute(
        text("""
            SELECT count(*) FROM demoforge.current_plan_items g
            JOIN demoforge.discovery_sessions s
              ON (s.workspace_id, s.id) = (g.workspace_id, g.session_id)
            WHERE s.workspace_id = :workspace AND s.opportunity_id = :opportunity
              AND g.kind = 'gap'
              AND (g.status <> 'resolved' OR g.approved_at IS NULL OR g.stale_source)
              AND EXISTS (
                  SELECT FROM demoforge.plan_affected_requirements link
                  JOIN demoforge.approved_storyboard_requirements q
                    ON (q.workspace_id, q.session_id, q.id) =
                       (link.workspace_id, link.session_id, link.requirement_id)
                  WHERE (link.workspace_id, link.session_id, link.item_id) =
                        (g.workspace_id, g.session_id, g.id)
                    AND (link.revision = g.revision OR link.revision = (
                        SELECT max(a.revision) FROM demoforge.plan_approvals a
                        WHERE (a.workspace_id, a.session_id, a.item_id) =
                              (g.workspace_id, g.session_id, g.id)
                    ))
              )
        """),
        scope,
    ).scalar_one()
    states = preparation_states(connection, scope, studio.storyboard.revision)
    return assess(studio, current, unresolved, states, archived=opportunity.archived_at is not None)
