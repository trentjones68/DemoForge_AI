"""Storyboard persistence and provenance reads using the scoped API connection."""

from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping

from demoforge_api.storyboard.models import (
    MAX_SCENES,
    Brief,
    CatalogRef,
    Evidence,
    Gap,
    ReleaseRef,
    RevisionAction,
    RevisionSummary,
    Scene,
    Storyboard,
    StoryboardSummary,
    Studio,
)
from demoforge_api.storyboard.planner import SUPPORT_WARNING, SceneInput

Scope = dict[str, UUID]
OPPORTUNITY = "workspace_id = :workspace AND opportunity_id = :opportunity"
CATALOG_COLUMNS = """
    CASE WHEN c.id IS NOT NULL THEN jsonb_build_object(
        'id', c.id, 'revision', c.revision, 'name', c.name, 'source_title', c.source_title,
        'source_url', c.source_url, 'source_locator', c.source_locator,
        'limitations', c.limitations, 'dependencies', c.dependencies
    ) END AS capability
"""


def evidence_from_row(row: RowMapping) -> Evidence:
    values = dict(row)
    values["capability"] = (
        CatalogRef.model_validate(row["capability"], strict=False) if row["capability"] else None
    )
    return Evidence.model_validate({key: values[key] for key in Evidence.model_fields})


def source_gaps(connection: Connection, scope: Scope) -> dict[tuple[UUID, UUID], list[Gap]]:
    rows = connection.execute(
        text("""
        SELECT g.session_id, a.requirement_id, g.id, g.revision, g.statement AS question,
               g.priority, g.status
        FROM demoforge.current_plan_items g
        JOIN demoforge.discovery_sessions s
          ON (s.workspace_id, s.id) = (g.workspace_id, g.session_id)
        JOIN demoforge.plan_affected_requirements a
          ON (a.workspace_id, a.session_id, a.item_id, a.revision) =
             (g.workspace_id, g.session_id, g.id, g.revision)
        WHERE s.workspace_id = :workspace AND s.opportunity_id = :opportunity
          AND g.kind = 'gap' AND g.status IN ('open', 'in_progress')
          AND g.approved_at IS NOT NULL AND NOT g.stale_source
        ORDER BY CASE g.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, g.id
    """),
        scope,
    ).mappings()
    grouped: dict[tuple[UUID, UUID], list[Gap]] = defaultdict(list)
    for row in rows:
        gaps = grouped[row["session_id"], row["requirement_id"]]
        gaps.append(Gap.model_validate({key: row[key] for key in Gap.model_fields}))
    return grouped


def eligible_inputs(
    connection: Connection, scope: Scope, *, scene: Scene | None = None
) -> list[SceneInput]:
    selector = "" if scene is None else "AND (q.session_id, q.id) = (:session, :requirement)"
    params = (
        scope
        if scene is None
        else scope
        | {
            "session": scene.evidence.session_id,
            "requirement": scene.evidence.requirement_id,
        }
    )
    rows = (
        connection.execute(
            text(f"""
        SELECT q.session_id, q.id AS requirement_id, q.revision AS requirement_revision,
               q.statement AS requirement, q.priority, m.id AS mapping_id,
               m.revision AS mapping_revision, m.support_status, m.rationale AS mapping_rationale,
               {CATALOG_COLUMNS}
        FROM demoforge.approved_storyboard_requirements q
        LEFT JOIN demoforge.reviewed_storyboard_mappings m
          ON (m.workspace_id, m.opportunity_id, m.session_id, m.requirement_id,
              m.requirement_revision) = (q.workspace_id, q.opportunity_id, q.session_id, q.id,
                                          q.revision) AND m.release_id = :release
        LEFT JOIN demoforge.catalog_capabilities c
          ON (c.workspace_id, c.release_id, c.id, c.revision) =
             (m.workspace_id, m.release_id, m.capability_id, m.capability_revision)
        WHERE q.workspace_id = :workspace AND q.opportunity_id = :opportunity {selector}
        LIMIT :limit
    """),
            params | {"limit": MAX_SCENES + 1},
        )
        .mappings()
        .all()
    )
    if not rows:
        raise HTTPException(409, "Approve a discovery requirement before planning its scene.")
    if len(rows) > MAX_SCENES:
        raise HTTPException(409, f"Demo Studio supports up to {MAX_SCENES} approved requirements.")
    if any(row["mapping_id"] is None for row in rows):
        raise HTTPException(
            409, "Review current capability mappings for the approved requirements in this release."
        )
    gaps = source_gaps(connection, scope)
    return [
        SceneInput(evidence_from_row(row), gaps.get((row["session_id"], row["requirement_id"]), []))
        for row in rows
    ]


def list_storyboards(connection: Connection, scope: Scope) -> list[StoryboardSummary]:
    rows = connection.execute(
        text("""
        SELECT b.id, b.audience, r.product, r.version, r.id AS release_id,
               (SELECT max(v.revision) FROM demoforge.storyboard_revisions v
                WHERE (v.workspace_id, v.opportunity_id, v.storyboard_id) =
                      (b.workspace_id, b.opportunity_id, b.id)) AS revision
        FROM demoforge.storyboards b
        JOIN demoforge.catalog_releases r ON (r.workspace_id, r.id) = (b.workspace_id, b.release_id)
        WHERE b.workspace_id = :workspace AND b.opportunity_id = :opportunity
        ORDER BY lower(b.audience), b.id
    """),
        scope,
    ).mappings()
    return [
        StoryboardSummary(
            id=row["id"],
            audience=row["audience"],
            revision=row["revision"],
            release=ReleaseRef(
                id=row["release_id"], product=row["product"], version=row["version"]
            ),
        )
        for row in rows
    ]


def load_studio(connection: Connection, scope: Scope, revision: int | None = None) -> Studio:
    row = (
        connection.execute(
            text("""
        SELECT b.audience, b.target_minutes, b.business_outcomes, r.product, r.version,
               r.id AS release_id
        FROM demoforge.storyboards b
        JOIN demoforge.catalog_releases r ON (r.workspace_id, r.id) = (b.workspace_id, b.release_id)
        WHERE b.workspace_id = :workspace AND b.opportunity_id = :opportunity AND b.id = :storyboard
    """),
            scope,
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Storyboard not found.")
    brief = Brief.model_validate({key: row[key] for key in Brief.model_fields})
    release = ReleaseRef(id=row["release_id"], product=row["product"], version=row["version"])
    rows = connection.execute(
        text("""
        SELECT v.revision, v.action, v.actor_id, v.created_at, a.approved_at,
               a.actor_id AS approved_by
        FROM demoforge.storyboard_revisions v
        LEFT JOIN demoforge.storyboard_approvals a USING (workspace_id, opportunity_id,
                                                        storyboard_id, revision)
        WHERE v.workspace_id = :workspace AND v.opportunity_id = :opportunity
          AND v.storyboard_id = :storyboard
        ORDER BY v.revision DESC
    """),
        scope,
    ).mappings()
    revisions = [RevisionSummary.model_validate(dict(row)) for row in rows]
    selected = next(
        (item for item in revisions if revision is None or item.revision == revision), None
    )
    if selected is None:
        raise HTTPException(404, "Storyboard revision not found.")
    storyboard = Storyboard(
        **selected.model_dump(),
        id=scope["storyboard"],
        brief=brief,
        release=release,
        scenes=load_scenes(connection, scope, selected.revision),
    )
    return Studio(
        current_revision=revisions[0].revision, revisions=revisions, storyboard=storyboard
    )


def load_scenes(connection: Connection, scope: Scope, revision: int) -> list[Scene]:
    params = scope | {"revision": revision}
    gaps = connection.execute(
        text("""
        SELECT g.scene_id, g.gap_id AS id, g.gap_revision AS revision,
               p.statement AS question, p.priority, p.status
        FROM demoforge.storyboard_scene_gaps g
        JOIN demoforge.plan_revisions p ON (p.workspace_id, p.session_id, p.item_id, p.revision) =
            (g.workspace_id, g.session_id, g.gap_id, g.gap_revision)
        WHERE g.workspace_id = :workspace AND g.opportunity_id = :opportunity
          AND g.storyboard_id = :storyboard AND g.revision = :revision
        ORDER BY CASE p.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, g.gap_id
    """),
        params,
    ).mappings()
    grouped: dict[UUID, list[Gap]] = defaultdict(list)
    for gap in gaps:
        grouped[gap["scene_id"]].append(
            Gap.model_validate({key: gap[key] for key in Gap.model_fields})
        )
    rows = connection.execute(
        text(f"""
        SELECT s.id, s.minutes, s.content, s.edited_fields, m.session_id, m.requirement_id,
               m.requirement_revision, q.statement AS requirement, q.priority, s.mapping_id,
               s.mapping_revision, mr.support_status, mr.rationale AS mapping_rationale,
               reviewed.id IS NULL AS stale_evidence, {CATALOG_COLUMNS}
        FROM demoforge.storyboard_scenes s
        JOIN demoforge.capability_mappings m
          ON (m.workspace_id, m.opportunity_id, m.release_id, m.id) =
             (s.workspace_id, s.opportunity_id, s.release_id, s.mapping_id)
        JOIN demoforge.plan_revisions q ON (q.workspace_id, q.session_id, q.item_id, q.revision) =
             (m.workspace_id, m.session_id, m.requirement_id, m.requirement_revision)
        JOIN demoforge.mapping_revisions mr
          ON (mr.workspace_id, mr.opportunity_id, mr.release_id, mr.mapping_id, mr.revision) =
             (s.workspace_id, s.opportunity_id, s.release_id, s.mapping_id, s.mapping_revision)
        LEFT JOIN demoforge.reviewed_storyboard_mappings reviewed
          ON (reviewed.workspace_id, reviewed.opportunity_id, reviewed.release_id,
              reviewed.id, reviewed.revision) =
             (s.workspace_id, s.opportunity_id, s.release_id, s.mapping_id, s.mapping_revision)
        LEFT JOIN demoforge.catalog_capabilities c
          ON (c.workspace_id, c.release_id, c.id, c.revision) =
             (mr.workspace_id, mr.release_id, mr.capability_id, mr.capability_revision)
        WHERE s.workspace_id = :workspace AND s.opportunity_id = :opportunity
          AND s.storyboard_id = :storyboard AND s.revision = :revision
        ORDER BY s.position
    """),
        params,
    ).mappings()
    return [
        Scene(
            id=row["id"],
            minutes=row["minutes"],
            content=row["content"],
            edited_fields=row["edited_fields"],
            evidence=evidence_from_row(row),
            gaps=grouped[row["id"]],
            stale_evidence=row["stale_evidence"],
            support_warning=SUPPORT_WARNING[row["support_status"]],
        )
        for row in rows
    ]


def append_revision(
    connection: Connection,
    scope: Scope,
    release_id: UUID,
    scenes: list[Scene],
    action: RevisionAction,
    revision: int,
) -> Storyboard:
    params = scope | {"revision": revision, "release": release_id}
    connection.execute(
        text("""
        INSERT INTO demoforge.storyboard_revisions
            (workspace_id, opportunity_id, release_id, storyboard_id, revision, action)
        VALUES (:workspace, :opportunity, :release, :storyboard, :revision, :action)
    """),
        params | {"action": action},
    )
    connection.execute(
        text("""
        INSERT INTO demoforge.storyboard_scenes
            (workspace_id, opportunity_id, release_id, storyboard_id, revision,
             id, position, minutes, session_id, requirement_id, mapping_id, mapping_revision,
             content, edited_fields)
        VALUES (:workspace, :opportunity, :release, :storyboard, :revision,
                :id, :position, :minutes, :session, :requirement, :mapping, :mapping_revision,
                CAST(:content AS jsonb), :edited_fields)
    """),
        [
            params
            | {
                "id": scene.id,
                "position": position,
                "minutes": scene.minutes,
                "session": scene.evidence.session_id,
                "requirement": scene.evidence.requirement_id,
                "mapping": scene.evidence.mapping_id,
                "mapping_revision": scene.evidence.mapping_revision,
                "content": scene.content.model_dump_json(),
                "edited_fields": scene.edited_fields,
            }
            for position, scene in enumerate(scenes, 1)
        ],
    )
    gaps = [
        params
        | {
            "scene": scene.id,
            "session": scene.evidence.session_id,
            "requirement": scene.evidence.requirement_id,
            "gap": gap.id,
            "gap_revision": gap.revision,
        }
        for scene in scenes
        for gap in scene.gaps
    ]
    if gaps:
        connection.execute(
            text("""
            INSERT INTO demoforge.storyboard_scene_gaps
                (workspace_id, opportunity_id, storyboard_id, revision, scene_id, session_id,
                 requirement_id, gap_id, gap_revision)
            VALUES (:workspace, :opportunity, :storyboard, :revision, :scene, :session,
                    :requirement, :gap, :gap_revision)
        """),
            gaps,
        )
    return load_studio(connection, scope, revision).storyboard
