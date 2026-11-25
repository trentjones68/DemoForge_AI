"""Revision-scoped demo preparation and download audit events."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE demoforge.storyboard_prep_events (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision integer NOT NULL,
            id bigint GENERATED ALWAYS AS IDENTITY,
            task text NOT NULL CHECK (task IN ('synthetic_data', 'rehearsal', 'risk_review')),
            complete boolean NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, revision, task, id),
            FOREIGN KEY (workspace_id, opportunity_id, storyboard_id, revision)
                REFERENCES demoforge.storyboard_revisions
                    (workspace_id, opportunity_id, storyboard_id, revision)
        );
        ALTER TABLE demoforge.storyboard_prep_events ENABLE ROW LEVEL SECURITY;
        CREATE POLICY prep_read ON demoforge.storyboard_prep_events FOR SELECT TO demoforge_api
            USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer'));
        CREATE POLICY prep_write ON demoforge.storyboard_prep_events FOR INSERT TO demoforge_api
            WITH CHECK (demoforge.can_write_discovery(workspace_id, opportunity_id) AND NOT EXISTS (
                SELECT FROM demoforge.storyboard_revisions later
                WHERE (later.workspace_id, later.opportunity_id, later.storyboard_id) =
                      (storyboard_prep_events.workspace_id, storyboard_prep_events.opportunity_id,
                       storyboard_prep_events.storyboard_id)
                  AND later.revision > storyboard_prep_events.revision
            ));
        GRANT SELECT ON demoforge.storyboard_prep_events TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, storyboard_id, revision, task, complete)
            ON demoforge.storyboard_prep_events TO demoforge_api;

        CREATE TABLE demoforge.storyboard_export_events (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            storyboard_id uuid NOT NULL,
            revision integer NOT NULL,
            delivery_id uuid NOT NULL,
            event text NOT NULL CHECK (event IN ('export_generated', 'artifact_accessed')),
            format text NOT NULL CHECK (format IN ('md', 'pdf')),
            byte_count integer NOT NULL CHECK (byte_count BETWEEN 1 AND 4194304),
            demo_ready boolean NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, opportunity_id, storyboard_id, delivery_id, event),
            FOREIGN KEY (workspace_id, opportunity_id, storyboard_id, revision)
                REFERENCES demoforge.storyboard_approvals
                    (workspace_id, opportunity_id, storyboard_id, revision)
        );
        ALTER TABLE demoforge.storyboard_export_events ENABLE ROW LEVEL SECURITY;
        CREATE POLICY export_record ON demoforge.storyboard_export_events
            FOR INSERT TO demoforge_api WITH CHECK (
                demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer')
                AND EXISTS (
                    SELECT FROM demoforge.storyboard_approvals approved
                    WHERE (approved.workspace_id, approved.opportunity_id, approved.storyboard_id,
                           approved.revision) =
                          (storyboard_export_events.workspace_id,
                           storyboard_export_events.opportunity_id,
                           storyboard_export_events.storyboard_id,
                           storyboard_export_events.revision)
                )
            );
        GRANT INSERT (workspace_id, opportunity_id, storyboard_id, revision, delivery_id, event,
                      format, byte_count, demo_ready)
            ON demoforge.storyboard_export_events TO demoforge_api;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE demoforge.storyboard_export_events, demoforge.storyboard_prep_events")
