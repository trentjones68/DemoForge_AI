"""Persist append-only storyboards with scoped, reviewed provenance."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE demoforge.capability_mappings ADD CONSTRAINT mapping_requirement_scope
            UNIQUE (workspace_id, opportunity_id, release_id, id, session_id, requirement_id);

        CREATE TABLE demoforge.storyboards (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            id uuid NOT NULL,
            audience text NOT NULL CHECK (char_length(btrim(audience)) BETWEEN 1 AND 160),
            target_minutes int NOT NULL CHECK (target_minutes BETWEEN 1 AND 180),
            business_outcomes text[] NOT NULL
                CHECK (cardinality(business_outcomes) BETWEEN 1 AND 5),
            PRIMARY KEY (workspace_id, opportunity_id, id),
            UNIQUE (workspace_id, opportunity_id, release_id, id),
            FOREIGN KEY (workspace_id, release_id)
                REFERENCES demoforge.catalog_releases(workspace_id, id),
            FOREIGN KEY (workspace_id, opportunity_id)
                REFERENCES demoforge.opportunities(workspace_id, id)
        );

        CREATE TABLE demoforge.storyboard_revisions (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision int NOT NULL CHECK (revision BETWEEN 1 AND 250),
            action text NOT NULL CHECK (action IN (
                'generated', 'scene_edited', 'agenda_updated', 'scene_regenerated'
            )),
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, revision),
            UNIQUE (workspace_id, opportunity_id, release_id, storyboard_id, revision),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, storyboard_id)
                REFERENCES demoforge.storyboards(workspace_id, opportunity_id, release_id, id)
        );

        CREATE TABLE demoforge.storyboard_scenes (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision int NOT NULL,
            id uuid NOT NULL,
            position int NOT NULL CHECK (position BETWEEN 1 AND 40),
            minutes int NOT NULL CHECK (minutes BETWEEN 1 AND 180),
            session_id uuid NOT NULL,
            requirement_id uuid NOT NULL,
            mapping_id uuid NOT NULL,
            mapping_revision int NOT NULL,
            content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
            edited_fields text[] NOT NULL CHECK (edited_fields <@ ARRAY[
                'title', 'actions', 'talk_track', 'expected_outcome', 'synthetic_data', 'risks'
            ]),
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, revision, id),
            UNIQUE (workspace_id, opportunity_id, storyboard_id, revision, position),
            UNIQUE (workspace_id, opportunity_id, storyboard_id, revision, session_id,
                    requirement_id),
            UNIQUE (workspace_id, opportunity_id, storyboard_id, revision, id, session_id,
                    requirement_id),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, storyboard_id, revision)
                REFERENCES demoforge.storyboard_revisions
                    (workspace_id, opportunity_id, release_id, storyboard_id, revision),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, mapping_id, session_id,
                         requirement_id) REFERENCES demoforge.capability_mappings
                    (workspace_id, opportunity_id, release_id, id, session_id, requirement_id),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, mapping_id, mapping_revision)
                REFERENCES demoforge.mapping_reviews
                    (workspace_id, opportunity_id, release_id, mapping_id, revision)
        );

        CREATE TABLE demoforge.storyboard_scene_gaps (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision int NOT NULL,
            scene_id uuid NOT NULL,
            session_id uuid NOT NULL,
            requirement_id uuid NOT NULL,
            gap_id uuid NOT NULL,
            gap_revision int NOT NULL,
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, revision, scene_id, gap_id),
            FOREIGN KEY (workspace_id, opportunity_id, storyboard_id, revision, scene_id,
                         session_id, requirement_id) REFERENCES demoforge.storyboard_scenes
                    (workspace_id, opportunity_id, storyboard_id, revision, id,
                     session_id, requirement_id),
            FOREIGN KEY (workspace_id, session_id, gap_id, gap_revision, requirement_id)
                REFERENCES demoforge.plan_affected_requirements
                    (workspace_id, session_id, item_id, revision, requirement_id),
            FOREIGN KEY (workspace_id, session_id, gap_id, gap_revision)
                REFERENCES demoforge.plan_approvals(workspace_id, session_id, item_id, revision)
        );

        CREATE TABLE demoforge.storyboard_approvals (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision int NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            approved_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            warnings_acknowledged boolean NOT NULL,
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, revision),
            FOREIGN KEY (workspace_id, opportunity_id, storyboard_id, revision)
                REFERENCES demoforge.storyboard_revisions
                    (workspace_id, opportunity_id, storyboard_id, revision)
        );

        CREATE FUNCTION demoforge.check_storyboard_agenda() RETURNS trigger
        LANGUAGE plpgsql SET search_path = '' AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM demoforge.storyboards b
                JOIN demoforge.storyboard_scenes s
                  ON (s.workspace_id, s.opportunity_id, s.storyboard_id) =
                     (b.workspace_id, b.opportunity_id, b.id)
                WHERE (b.workspace_id, b.opportunity_id, b.id, s.revision) =
                      (NEW.workspace_id, NEW.opportunity_id, NEW.storyboard_id, NEW.revision)
                GROUP BY b.target_minutes
                HAVING sum(s.minutes) = b.target_minutes AND count(*) = max(s.position)
            ) THEN
                RAISE check_violation USING MESSAGE = 'Invalid storyboard agenda';
            END IF;
            RETURN NULL;
        END $$;

        CREATE CONSTRAINT TRIGGER storyboard_revision_agenda
            AFTER INSERT ON demoforge.storyboard_revisions DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION demoforge.check_storyboard_agenda();
        CREATE CONSTRAINT TRIGGER storyboard_scene_agenda
            AFTER INSERT ON demoforge.storyboard_scenes DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION demoforge.check_storyboard_agenda();
    """)
    tables = (
        "storyboards",
        "storyboard_revisions",
        "storyboard_scenes",
        "storyboard_scene_gaps",
        "storyboard_approvals",
    )
    for table in tables:
        op.execute(f"""
            ALTER TABLE demoforge.{table} ENABLE ROW LEVEL SECURITY;
            GRANT SELECT ON demoforge.{table} TO demoforge_api;
            CREATE POLICY storyboard_read ON demoforge.{table} FOR SELECT TO demoforge_api
                USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer'));
            CREATE POLICY storyboard_write ON demoforge.{table} FOR INSERT TO demoforge_api
                WITH CHECK (demoforge.can_write_discovery(workspace_id, opportunity_id));
        """)
    op.execute("""
        CREATE POLICY approve_fresh_storyboard ON demoforge.storyboard_approvals
            AS RESTRICTIVE FOR INSERT TO demoforge_api WITH CHECK (
                NOT EXISTS (
                    SELECT FROM demoforge.storyboard_revisions newer
                    WHERE (newer.workspace_id, newer.opportunity_id, newer.storyboard_id) =
                          (storyboard_approvals.workspace_id, storyboard_approvals.opportunity_id,
                           storyboard_approvals.storyboard_id)
                      AND newer.revision > storyboard_approvals.revision
                )
                AND EXISTS (
                    SELECT FROM demoforge.storyboard_scenes s
                    WHERE (s.workspace_id, s.opportunity_id, s.storyboard_id, s.revision) =
                          (storyboard_approvals.workspace_id, storyboard_approvals.opportunity_id,
                           storyboard_approvals.storyboard_id, storyboard_approvals.revision)
                )
                AND NOT EXISTS (
                    SELECT FROM demoforge.storyboard_scenes s
                    WHERE (s.workspace_id, s.opportunity_id, s.storyboard_id, s.revision) =
                          (storyboard_approvals.workspace_id, storyboard_approvals.opportunity_id,
                           storyboard_approvals.storyboard_id, storyboard_approvals.revision)
                      AND NOT EXISTS (
                          SELECT FROM demoforge.reviewed_storyboard_mappings m
                          WHERE (m.workspace_id, m.opportunity_id, m.release_id, m.id, m.revision) =
                                (s.workspace_id, s.opportunity_id, s.release_id, s.mapping_id,
                                 s.mapping_revision)
                      )
                )
                AND (warnings_acknowledged OR NOT EXISTS (
                    SELECT FROM demoforge.storyboard_scenes s
                    JOIN demoforge.mapping_revisions m
                      ON (m.workspace_id, m.opportunity_id, m.release_id,
                          m.mapping_id, m.revision) =
                         (s.workspace_id, s.opportunity_id, s.release_id, s.mapping_id,
                          s.mapping_revision)
                    WHERE (s.workspace_id, s.opportunity_id, s.storyboard_id, s.revision) =
                          (storyboard_approvals.workspace_id, storyboard_approvals.opportunity_id,
                           storyboard_approvals.storyboard_id, storyboard_approvals.revision)
                      AND m.support_status <> 'supported'
                ))
            );

        GRANT INSERT (workspace_id, opportunity_id, release_id, id, audience, target_minutes,
                      business_outcomes) ON demoforge.storyboards TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, release_id, storyboard_id, revision, action)
            ON demoforge.storyboard_revisions TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, release_id, storyboard_id, revision, id,
                      position, minutes, session_id, requirement_id, mapping_id, mapping_revision,
                      content, edited_fields) ON demoforge.storyboard_scenes TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, storyboard_id, revision, scene_id, session_id,
                      requirement_id, gap_id, gap_revision)
            ON demoforge.storyboard_scene_gaps TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, storyboard_id, revision, warnings_acknowledged)
            ON demoforge.storyboard_approvals TO demoforge_api;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE demoforge.storyboard_approvals, demoforge.storyboard_scene_gaps,
                   demoforge.storyboard_scenes, demoforge.storyboard_revisions,
                   demoforge.storyboards;
        DROP FUNCTION demoforge.check_storyboard_agenda();
        ALTER TABLE demoforge.capability_mappings DROP CONSTRAINT mapping_requirement_scope;
    """)
