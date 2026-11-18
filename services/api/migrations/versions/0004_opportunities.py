"""Workspace-scoped opportunities and immutable audit events."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE demoforge.opportunities (
            workspace_id uuid NOT NULL REFERENCES demoforge.workspaces(id) ON DELETE CASCADE,
            id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
            owner_id uuid,
            name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
            company text NOT NULL CHECK (char_length(btrim(company)) BETWEEN 1 AND 120),
            stage text NOT NULL CHECK (stage IN (
                'discovery', 'qualification', 'demo_planning', 'demo_scheduled',
                'follow_up', 'closed_won', 'closed_lost'
            )),
            product text NOT NULL CHECK (char_length(btrim(product)) BETWEEN 1 AND 120),
            demo_date date CHECK (demo_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'),
            use_case text NOT NULL DEFAULT '' CHECK (char_length(use_case) <= 300),
            notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 5000),
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            PRIMARY KEY (workspace_id, id),
            FOREIGN KEY (workspace_id, owner_id)
                REFERENCES demoforge.memberships(workspace_id, user_id)
                ON DELETE SET NULL (owner_id)
        );

        CREATE INDEX opportunities_recent_idx
            ON demoforge.opportunities (workspace_id, updated_at DESC, id);
        CREATE INDEX opportunities_owner_idx
            ON demoforge.opportunities (workspace_id, owner_id);

        CREATE TABLE demoforge.opportunity_audit_events (
            workspace_id uuid NOT NULL,
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            opportunity_id uuid NOT NULL,
            actor_id uuid,
            action text NOT NULL CHECK (action IN ('created', 'updated', 'archived')),
            version integer NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            FOREIGN KEY (workspace_id, opportunity_id)
                REFERENCES demoforge.opportunities(workspace_id, id) ON DELETE CASCADE
        );
        CREATE INDEX opportunity_audit_target_idx
            ON demoforge.opportunity_audit_events (workspace_id, opportunity_id, id);

        ALTER TABLE demoforge.opportunities ENABLE ROW LEVEL SECURITY;
        ALTER TABLE demoforge.opportunity_audit_events ENABLE ROW LEVEL SECURITY;

        CREATE FUNCTION demoforge.opportunity_owner_eligible(target uuid, candidate uuid)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT demoforge.workspace_role(target) IN ('admin', 'sales_engineer')
                AND EXISTS (
                    SELECT FROM demoforge.memberships
                    WHERE workspace_id = target AND user_id = candidate
                        AND role IN ('admin', 'sales_engineer')
                )
        $$;

        REVOKE ALL ON FUNCTION demoforge.opportunity_owner_eligible(uuid, uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION demoforge.opportunity_owner_eligible(uuid, uuid)
            TO demoforge_api;

        CREATE FUNCTION demoforge.bump_opportunity_version() RETURNS trigger
        LANGUAGE plpgsql SET search_path = ''
        AS $$
        BEGIN
            IF current_user = 'demoforge_api' AND NEW.owner_id IS NOT NULL
                AND NEW.owner_id IS DISTINCT FROM OLD.owner_id
                AND NOT COALESCE(demoforge.opportunity_owner_eligible(
                    NEW.workspace_id, NEW.owner_id
                ), false)
            THEN
                RAISE EXCEPTION 'The requested owner is not eligible' USING ERRCODE = '42501';
            END IF;
            NEW.version := OLD.version + 1;
            NEW.updated_at := pg_catalog.statement_timestamp();
            RETURN NEW;
        END
        $$;
        CREATE FUNCTION demoforge.record_opportunity_change() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        BEGIN
            INSERT INTO demoforge.opportunity_audit_events
                (workspace_id, opportunity_id, actor_id, action, version)
            VALUES (
                NEW.workspace_id, NEW.id, demoforge.request_subject(),
                CASE
                    WHEN TG_OP = 'INSERT' THEN 'created'
                    WHEN OLD.archived_at IS NULL AND NEW.archived_at IS NOT NULL THEN 'archived'
                    ELSE 'updated'
                END,
                NEW.version
            );
            RETURN NULL;
        END
        $$;
        REVOKE ALL ON FUNCTION demoforge.bump_opportunity_version() FROM PUBLIC;
        REVOKE ALL ON FUNCTION demoforge.record_opportunity_change() FROM PUBLIC;

        CREATE TRIGGER opportunity_version BEFORE UPDATE ON demoforge.opportunities
            FOR EACH ROW EXECUTE FUNCTION demoforge.bump_opportunity_version();
        CREATE TRIGGER opportunity_audit AFTER INSERT OR UPDATE ON demoforge.opportunities
            FOR EACH ROW EXECUTE FUNCTION demoforge.record_opportunity_change();

        GRANT SELECT ON demoforge.opportunities, demoforge.opportunity_audit_events
            TO demoforge_api;
        GRANT INSERT (workspace_id, owner_id, name, company, stage, product,
            demo_date, use_case, notes)
            ON demoforge.opportunities TO demoforge_api;
        GRANT UPDATE (owner_id, name, company, stage, product, demo_date,
            use_case, notes, archived_at)
            ON demoforge.opportunities TO demoforge_api;

        CREATE POLICY opportunity_read ON demoforge.opportunities FOR SELECT TO demoforge_api
            USING (demoforge.workspace_role(workspace_id) IS NOT NULL);
        CREATE POLICY opportunity_create ON demoforge.opportunities FOR INSERT TO demoforge_api
            WITH CHECK (
                demoforge.opportunity_owner_eligible(workspace_id, owner_id)
                AND (demoforge.workspace_role(workspace_id) = 'admin'
                    OR owner_id = demoforge.request_subject())
            );
        CREATE POLICY opportunity_edit ON demoforge.opportunities FOR UPDATE TO demoforge_api
            USING (
                archived_at IS NULL AND (
                    demoforge.workspace_role(workspace_id) = 'admin'
                    OR (demoforge.workspace_role(workspace_id) = 'sales_engineer'
                        AND owner_id = demoforge.request_subject())
                )
            )
            WITH CHECK (
                demoforge.workspace_role(workspace_id) = 'admin'
                OR (demoforge.workspace_role(workspace_id) = 'sales_engineer'
                    AND owner_id = demoforge.request_subject())
            );
        CREATE POLICY opportunity_audit_read ON demoforge.opportunity_audit_events
            FOR SELECT TO demoforge_api USING (demoforge.workspace_role(workspace_id) = 'admin');
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE demoforge.opportunity_audit_events;
        DROP TABLE demoforge.opportunities;
        DROP FUNCTION demoforge.record_opportunity_change();
        DROP FUNCTION demoforge.bump_opportunity_version();
        DROP FUNCTION demoforge.opportunity_owner_eligible(uuid, uuid);
    """)
