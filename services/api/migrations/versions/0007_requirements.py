"""Versioned discovery requirements and follow-ups with an approved-only input view."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE demoforge.plan_items (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('requirement', 'gap')),
            normalization_key text,
            source_job_id uuid,
            source_finding_id uuid,
            source_revision int,
            PRIMARY KEY (workspace_id, session_id, id),
            UNIQUE (workspace_id, session_id, id, kind),
            UNIQUE (workspace_id, session_id, normalization_key),
            FOREIGN KEY (workspace_id, session_id)
                REFERENCES demoforge.discovery_sessions(workspace_id, id),
            FOREIGN KEY (
                workspace_id, session_id, source_job_id, source_finding_id, source_revision
            )
                REFERENCES demoforge.analysis_approvals
                    (workspace_id, session_id, job_id, finding_id, revision),
            CHECK (num_nonnulls(source_job_id, source_finding_id, source_revision) IN (0, 3)),
            CHECK (source_job_id IS NULL OR normalization_key IS NOT NULL),
            CHECK (kind <> 'requirement' OR normalization_key IS NULL OR source_job_id IS NOT NULL)
        );

        CREATE TABLE demoforge.plan_revisions (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            item_id uuid NOT NULL,
            kind text NOT NULL,
            revision int NOT NULL CHECK (revision BETWEEN 1 AND 2147483646),
            statement text NOT NULL CHECK (char_length(btrim(statement)) BETWEEN 1 AND 800),
            rationale text NOT NULL CHECK (char_length(btrim(rationale)) BETWEEN 1 AND 800),
            category text NOT NULL
                CHECK (category IN ('buyer', 'kpi', 'workflow', 'integration', 'general')),
            priority text NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
            owner_id uuid,
            status text,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, session_id, item_id, revision),
            FOREIGN KEY (workspace_id, session_id, item_id, kind)
                REFERENCES demoforge.plan_items(workspace_id, session_id, id, kind),
            CHECK (
                (kind = 'requirement' AND owner_id IS NULL AND status IS NULL)
                OR (kind = 'gap' AND status IS NOT NULL
                    AND status IN ('open', 'in_progress', 'resolved'))
            )
        );

        CREATE TABLE demoforge.plan_affected_requirements (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            item_id uuid NOT NULL,
            revision int NOT NULL,
            requirement_id uuid NOT NULL,
            target_kind text GENERATED ALWAYS AS ('requirement'::text) STORED,
            PRIMARY KEY (workspace_id, session_id, item_id, revision, requirement_id),
            FOREIGN KEY (workspace_id, session_id, item_id, revision)
                REFERENCES demoforge.plan_revisions(workspace_id, session_id, item_id, revision),
            FOREIGN KEY (workspace_id, session_id, requirement_id, target_kind)
                REFERENCES demoforge.plan_items(workspace_id, session_id, id, kind),
            CHECK (item_id <> requirement_id)
        );

        CREATE TABLE demoforge.plan_approvals (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            item_id uuid NOT NULL,
            revision int NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            approved_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, session_id, item_id, revision),
            FOREIGN KEY (workspace_id, session_id, item_id, revision)
                REFERENCES demoforge.plan_revisions(workspace_id, session_id, item_id, revision)
        );
    """)
    for table in ("plan_items", "plan_revisions", "plan_affected_requirements", "plan_approvals"):
        op.execute(f"""
            ALTER TABLE demoforge.{table} ENABLE ROW LEVEL SECURITY;
            GRANT SELECT ON demoforge.{table} TO demoforge_api;
            CREATE POLICY plan_read ON demoforge.{table} FOR SELECT TO demoforge_api
                USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer'));
        """)
    op.execute("""
        CREATE FUNCTION demoforge.plan_owners(target uuid)
        RETURNS TABLE (id uuid) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT m.user_id FROM demoforge.memberships m
            WHERE m.workspace_id = target AND m.role IN ('admin', 'sales_engineer')
              AND demoforge.workspace_role(target) IN ('admin', 'sales_engineer')
            ORDER BY m.user_id
        $$;
        REVOKE ALL ON FUNCTION demoforge.plan_owners(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION demoforge.plan_owners(uuid) TO demoforge_api;

        GRANT INSERT ON demoforge.plan_items TO demoforge_api;
        GRANT INSERT (
            workspace_id, session_id, item_id, kind, revision, statement, rationale,
            category, priority, owner_id, status
        ) ON demoforge.plan_revisions TO demoforge_api;
        GRANT INSERT (workspace_id, session_id, item_id, revision, requirement_id)
            ON demoforge.plan_affected_requirements TO demoforge_api;
        GRANT INSERT (workspace_id, session_id, item_id, revision)
            ON demoforge.plan_approvals TO demoforge_api;

        CREATE POLICY plan_create ON demoforge.plan_items FOR INSERT TO demoforge_api
            WITH CHECK (demoforge.can_write_discovery_source(workspace_id, session_id));
        CREATE POLICY plan_edit ON demoforge.plan_revisions FOR INSERT TO demoforge_api
            WITH CHECK (
                actor_id = demoforge.request_subject()
                AND demoforge.can_write_discovery_source(workspace_id, session_id)
                AND (owner_id IS NULL OR EXISTS (
                    SELECT FROM demoforge.plan_owners(workspace_id) o WHERE o.id = owner_id
                ))
            );
        CREATE POLICY plan_link ON demoforge.plan_affected_requirements
            FOR INSERT TO demoforge_api WITH CHECK (
                demoforge.can_write_discovery_source(workspace_id, session_id)
                AND EXISTS (
                    SELECT FROM demoforge.plan_items i
                    WHERE (i.workspace_id, i.session_id, i.id) =
                          (plan_affected_requirements.workspace_id,
                           plan_affected_requirements.session_id,
                           plan_affected_requirements.item_id) AND i.kind = 'gap'
                )
            );

        CREATE VIEW demoforge.current_approved_findings WITH (security_invoker = true) AS
            SELECT f.* FROM demoforge.analysis_findings f
            JOIN demoforge.analysis_approvals a
              ON (a.workspace_id, a.session_id, a.job_id, a.finding_id, a.revision) =
                 (f.workspace_id, f.session_id, f.job_id, f.id, f.revision)
            JOIN demoforge.analysis_jobs j
              ON (j.workspace_id, j.session_id, j.id) = (f.workspace_id, f.session_id, f.job_id)
            WHERE j.status = 'succeeded'
              AND NOT EXISTS (
                  SELECT FROM demoforge.analysis_findings newer
                  WHERE (newer.workspace_id, newer.session_id, newer.job_id, newer.id) =
                        (f.workspace_id, f.session_id, f.job_id, f.id)
                    AND newer.revision > f.revision
              );
        GRANT SELECT ON demoforge.current_approved_findings TO demoforge_api;

        CREATE VIEW demoforge.current_plan_items WITH (security_invoker = true) AS
            SELECT i.*, r.revision, r.statement, r.rationale, r.category, r.priority, r.owner_id,
                   r.status, r.actor_id, r.created_at, a.actor_id AS approved_by, a.approved_at,
                   (i.source_job_id IS NOT NULL AND f.id IS NULL) AS stale_source
            FROM demoforge.plan_items i
            JOIN LATERAL (
                SELECT * FROM demoforge.plan_revisions rr
                WHERE (rr.workspace_id, rr.session_id, rr.item_id) =
                      (i.workspace_id, i.session_id, i.id)
                ORDER BY rr.revision DESC LIMIT 1
            ) r ON true
            LEFT JOIN demoforge.plan_approvals a
              ON (a.workspace_id, a.session_id, a.item_id, a.revision) =
                 (r.workspace_id, r.session_id, r.item_id, r.revision)
            LEFT JOIN demoforge.current_approved_findings f
              ON (f.workspace_id, f.session_id, f.job_id, f.id, f.revision) =
                 (i.workspace_id, i.session_id, i.source_job_id, i.source_finding_id,
                  i.source_revision);
        GRANT SELECT ON demoforge.current_plan_items TO demoforge_api;

        CREATE POLICY plan_approve ON demoforge.plan_approvals FOR INSERT TO demoforge_api
            WITH CHECK (
                actor_id = demoforge.request_subject()
                AND demoforge.can_write_discovery_source(workspace_id, session_id)
                AND EXISTS (
                    SELECT FROM demoforge.plan_items i
                    JOIN demoforge.plan_revisions r
                      ON (r.workspace_id, r.session_id, r.item_id) =
                         (i.workspace_id, i.session_id, i.id)
                    WHERE (r.workspace_id, r.session_id, r.item_id, r.revision) =
                          (plan_approvals.workspace_id, plan_approvals.session_id,
                           plan_approvals.item_id, plan_approvals.revision)
                      AND NOT EXISTS (
                          SELECT FROM demoforge.plan_revisions newer
                          WHERE (newer.workspace_id, newer.session_id, newer.item_id) =
                                (r.workspace_id, r.session_id, r.item_id)
                            AND newer.revision > r.revision
                      )
                      AND (i.source_job_id IS NULL OR EXISTS (
                          SELECT FROM demoforge.current_approved_findings f
                          WHERE (f.workspace_id, f.session_id, f.job_id, f.id, f.revision) =
                                (i.workspace_id, i.session_id, i.source_job_id, i.source_finding_id,
                                 i.source_revision)
                      ))
                )
            );

        CREATE VIEW demoforge.approved_storyboard_requirements WITH (security_invoker = true) AS
            SELECT p.*, s.opportunity_id
            FROM demoforge.current_plan_items p
            JOIN demoforge.discovery_sessions s
              ON (s.workspace_id, s.id) = (p.workspace_id, p.session_id)
            WHERE p.kind = 'requirement' AND p.approved_at IS NOT NULL AND NOT p.stale_source;
        GRANT SELECT ON demoforge.approved_storyboard_requirements TO demoforge_api;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW demoforge.approved_storyboard_requirements, demoforge.current_plan_items;
        DROP TABLE demoforge.plan_approvals, demoforge.plan_affected_requirements,
            demoforge.plan_revisions, demoforge.plan_items;
        DROP VIEW demoforge.current_approved_findings;
        DROP FUNCTION demoforge.plan_owners(uuid);
    """)
