"""Versioned product evidence, reviewed mappings, and eligible downstream inputs."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE demoforge.discovery_sessions ADD CONSTRAINT discovery_session_opportunity_key
            UNIQUE (workspace_id, opportunity_id, id);

        CREATE TABLE demoforge.catalog_releases (
            workspace_id uuid NOT NULL REFERENCES demoforge.workspaces(id),
            id uuid NOT NULL,
            product text NOT NULL CHECK (char_length(btrim(product)) BETWEEN 1 AND 120),
            version text NOT NULL CHECK (char_length(btrim(version)) BETWEEN 1 AND 80),
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, id)
        );
        CREATE UNIQUE INDEX catalog_release_label
            ON demoforge.catalog_releases (workspace_id, lower(product), lower(version));

        CREATE TABLE demoforge.catalog_capabilities (
            workspace_id uuid NOT NULL,
            release_id uuid NOT NULL,
            id uuid NOT NULL,
            revision int NOT NULL CHECK (revision BETWEEN 1 AND 2147483646),
            name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
            description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 800),
            support_status text NOT NULL CHECK (
                support_status IN ('supported', 'partial', 'unsupported', 'unknown')
            ),
            limitations text NOT NULL CHECK (char_length(limitations) <= 800),
            dependencies text[] NOT NULL CHECK (cardinality(dependencies) <= 12),
            match_phrases text[] NOT NULL CHECK (cardinality(match_phrases) <= 12),
            source_title text NOT NULL CHECK (char_length(btrim(source_title)) BETWEEN 1 AND 200),
            source_url text NOT NULL CHECK (source_url LIKE 'https://%'
                AND char_length(source_url) <= 1200),
            source_locator text NOT NULL
                CHECK (char_length(btrim(source_locator)) BETWEEN 1 AND 200),
            archived boolean NOT NULL DEFAULT false,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, release_id, id, revision),
            UNIQUE (workspace_id, release_id, id, revision, support_status, archived),
            FOREIGN KEY (workspace_id, release_id)
                REFERENCES demoforge.catalog_releases(workspace_id, id),
            CHECK (support_status NOT IN ('partial', 'unsupported') OR btrim(limitations) <> '')
        );

        CREATE TABLE demoforge.capability_mappings (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            id uuid NOT NULL,
            session_id uuid NOT NULL,
            requirement_id uuid NOT NULL,
            requirement_revision int NOT NULL,
            requirement_kind text GENERATED ALWAYS AS ('requirement'::text) STORED,
            PRIMARY KEY (workspace_id, opportunity_id, release_id, id),
            UNIQUE (workspace_id, opportunity_id, release_id, session_id,
                    requirement_id, requirement_revision),
            FOREIGN KEY (workspace_id, release_id)
                REFERENCES demoforge.catalog_releases(workspace_id, id),
            FOREIGN KEY (workspace_id, opportunity_id, session_id)
                REFERENCES demoforge.discovery_sessions(workspace_id, opportunity_id, id),
            FOREIGN KEY (workspace_id, session_id, requirement_id, requirement_kind)
                REFERENCES demoforge.plan_items(workspace_id, session_id, id, kind),
            FOREIGN KEY (workspace_id, session_id, requirement_id, requirement_revision)
                REFERENCES demoforge.plan_approvals(workspace_id, session_id, item_id, revision)
        );

        CREATE TABLE demoforge.mapping_revisions (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            mapping_id uuid NOT NULL,
            revision int NOT NULL CHECK (revision BETWEEN 1 AND 2147483646),
            capability_id uuid,
            capability_revision int,
            capability_archived boolean GENERATED ALWAYS AS (false) STORED,
            support_status text NOT NULL CHECK (
                support_status IN ('supported', 'partial', 'unsupported', 'unknown')
            ),
            rationale text NOT NULL CHECK (char_length(btrim(rationale)) BETWEEN 1 AND 800),
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, opportunity_id, release_id, mapping_id, revision),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, mapping_id)
                REFERENCES demoforge.capability_mappings
                    (workspace_id, opportunity_id, release_id, id),
            FOREIGN KEY (workspace_id, release_id, capability_id, capability_revision,
                         support_status, capability_archived)
                REFERENCES demoforge.catalog_capabilities
                    (workspace_id, release_id, id, revision, support_status, archived),
            CHECK ((capability_id IS NULL AND capability_revision IS NULL
                    AND support_status = 'unknown')
                   OR (capability_id IS NOT NULL AND capability_revision IS NOT NULL))
        );

        CREATE TABLE demoforge.mapping_reviews (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            release_id uuid NOT NULL,
            mapping_id uuid NOT NULL,
            revision int NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            reviewed_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, opportunity_id, release_id, mapping_id, revision),
            FOREIGN KEY (workspace_id, opportunity_id, release_id, mapping_id, revision)
                REFERENCES demoforge.mapping_revisions
                    (workspace_id, opportunity_id, release_id, mapping_id, revision)
        );

        CREATE VIEW demoforge.current_catalog_capabilities WITH (security_invoker = true) AS
            SELECT DISTINCT ON (workspace_id, release_id, id) *
            FROM demoforge.catalog_capabilities
            ORDER BY workspace_id, release_id, id, revision DESC;

        CREATE VIEW demoforge.current_capability_mappings WITH (security_invoker = true) AS
            SELECT m.*, requirement.statement AS requirement_statement, latest.revision,
                   latest.capability_id, latest.capability_revision,
                   latest.support_status, latest.rationale, latest.actor_id, latest.created_at,
                   r.actor_id AS reviewed_by, r.reviewed_at,
                   (latest.capability_id IS NOT NULL
                    AND (available.revision IS DISTINCT FROM latest.capability_revision
                         OR available.archived)) AS stale_evidence
            FROM demoforge.capability_mappings m
            JOIN LATERAL (
                SELECT * FROM demoforge.mapping_revisions mr
                WHERE (mr.workspace_id, mr.opportunity_id, mr.release_id, mr.mapping_id) =
                      (m.workspace_id, m.opportunity_id, m.release_id, m.id)
                ORDER BY mr.revision DESC LIMIT 1
            ) latest ON true
            LEFT JOIN demoforge.mapping_reviews r
              ON (r.workspace_id, r.opportunity_id, r.release_id, r.mapping_id, r.revision) =
                 (m.workspace_id, m.opportunity_id, m.release_id, m.id, latest.revision)
            LEFT JOIN demoforge.current_catalog_capabilities available
              ON (available.workspace_id, available.release_id, available.id) =
                 (m.workspace_id, m.release_id, latest.capability_id)
            JOIN demoforge.approved_storyboard_requirements requirement
              ON (requirement.workspace_id, requirement.opportunity_id, requirement.session_id,
                  requirement.id, requirement.revision) =
                 (m.workspace_id, m.opportunity_id, m.session_id,
                  m.requirement_id, m.requirement_revision);

        CREATE VIEW demoforge.reviewed_storyboard_mappings WITH (security_invoker = true) AS
            SELECT * FROM demoforge.current_capability_mappings
            WHERE reviewed_at IS NOT NULL AND NOT stale_evidence;

        GRANT SELECT ON demoforge.current_catalog_capabilities,
            demoforge.current_capability_mappings, demoforge.reviewed_storyboard_mappings
            TO demoforge_api;
    """)
    add_policies()


def add_policies() -> None:
    for table in ("catalog_releases", "catalog_capabilities"):
        op.execute(f"""
            ALTER TABLE demoforge.{table} ENABLE ROW LEVEL SECURITY;
            GRANT SELECT ON demoforge.{table} TO demoforge_api;
            CREATE POLICY catalog_read ON demoforge.{table} FOR SELECT TO demoforge_api
                USING (demoforge.workspace_role(workspace_id) IN (
                    'admin', 'product_admin', 'sales_engineer'
                ));
            CREATE POLICY catalog_write ON demoforge.{table} FOR INSERT TO demoforge_api
                WITH CHECK (
                    demoforge.workspace_role(workspace_id) IN ('admin', 'product_admin')
                    AND actor_id = demoforge.request_subject()
                );
        """)
    for table in ("capability_mappings", "mapping_revisions", "mapping_reviews"):
        op.execute(f"""
            ALTER TABLE demoforge.{table} ENABLE ROW LEVEL SECURITY;
            GRANT SELECT ON demoforge.{table} TO demoforge_api;
            CREATE POLICY mapping_read ON demoforge.{table} FOR SELECT TO demoforge_api
                USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer'));
            CREATE POLICY mapping_write ON demoforge.{table} FOR INSERT TO demoforge_api
                WITH CHECK (demoforge.can_write_discovery(workspace_id, opportunity_id));
        """)
    op.execute("""
        CREATE POLICY mapping_current_requirement ON demoforge.capability_mappings
            AS RESTRICTIVE FOR INSERT TO demoforge_api WITH CHECK (
                EXISTS (
                    SELECT FROM demoforge.approved_storyboard_requirements q
                    WHERE (q.workspace_id, q.opportunity_id, q.session_id, q.id, q.revision) =
                          (capability_mappings.workspace_id, capability_mappings.opportunity_id,
                           capability_mappings.session_id, capability_mappings.requirement_id,
                           capability_mappings.requirement_revision)
                )
            );

        GRANT INSERT (workspace_id, id, product, version)
            ON demoforge.catalog_releases TO demoforge_api;
        GRANT INSERT (workspace_id, release_id, id, revision, name, description, support_status,
                      limitations, dependencies, match_phrases, source_title, source_url,
                      source_locator, archived)
            ON demoforge.catalog_capabilities TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, release_id, id,
                      session_id, requirement_id, requirement_revision)
            ON demoforge.capability_mappings TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, release_id, mapping_id, revision,
                      capability_id, capability_revision, support_status, rationale)
            ON demoforge.mapping_revisions TO demoforge_api;
        GRANT INSERT (workspace_id, opportunity_id, release_id, mapping_id, revision)
            ON demoforge.mapping_reviews TO demoforge_api;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW demoforge.reviewed_storyboard_mappings, demoforge.current_capability_mappings,
                  demoforge.current_catalog_capabilities;
        DROP TABLE demoforge.mapping_reviews, demoforge.mapping_revisions,
                   demoforge.capability_mappings, demoforge.catalog_capabilities,
                   demoforge.catalog_releases;
        ALTER TABLE demoforge.discovery_sessions DROP CONSTRAINT discovery_session_opportunity_key;
    """)
