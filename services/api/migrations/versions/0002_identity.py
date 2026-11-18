"""Workspaces and scoped memberships."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF current_user = 'demoforge_api' OR NOT EXISTS (
                SELECT FROM pg_roles WHERE rolname = 'demoforge_api'
                    AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
                    AND NOT rolcreaterole AND NOT rolcreatedb
            ) THEN
                RAISE EXCEPTION 'Provision a separate restricted demoforge_api login first';
            END IF;
        END
        $$;

        CREATE SCHEMA demoforge;
        REVOKE ALL ON SCHEMA demoforge FROM PUBLIC;
        GRANT USAGE ON SCHEMA demoforge TO demoforge_api;

        CREATE TABLE demoforge.workspaces (
            id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
            name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 100)
        );

        CREATE TABLE demoforge.memberships (
            workspace_id uuid NOT NULL REFERENCES demoforge.workspaces(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            role text NOT NULL
                CHECK (role IN ('admin', 'product_admin', 'sales_engineer', 'viewer')),
            PRIMARY KEY (workspace_id, user_id)
        );
        CREATE INDEX memberships_user_id_idx ON demoforge.memberships (user_id);

        ALTER TABLE demoforge.workspaces ENABLE ROW LEVEL SECURITY;
        ALTER TABLE demoforge.memberships ENABLE ROW LEVEL SECURITY;

        CREATE FUNCTION demoforge.request_subject() RETURNS uuid
        LANGUAGE sql STABLE
        SET search_path = ''
        AS $$
            SELECT nullif(pg_catalog.current_setting('demoforge.user_id', true), '')::uuid
        $$;

        -- Only the migration owner can bypass RLS inside these narrowly scoped functions.
        CREATE FUNCTION demoforge.workspace_role(target uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT role FROM demoforge.memberships
            WHERE workspace_id = target AND user_id = demoforge.request_subject()
        $$;

        CREATE FUNCTION demoforge.create_workspace(workspace_name text) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
            subject uuid := demoforge.request_subject();
            workspace uuid;
        BEGIN
            IF subject IS NULL THEN
                RAISE EXCEPTION 'User identity required' USING ERRCODE = '42501';
            END IF;
            INSERT INTO demoforge.workspaces (name)
            VALUES (workspace_name) RETURNING id INTO workspace;
            INSERT INTO demoforge.memberships (workspace_id, user_id, role)
            VALUES (workspace, subject, 'admin');
            RETURN workspace;
        END
        $$;

        REVOKE ALL ON FUNCTION demoforge.request_subject() FROM PUBLIC;
        REVOKE ALL ON FUNCTION demoforge.workspace_role(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION demoforge.create_workspace(text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION demoforge.request_subject(),
            demoforge.workspace_role(uuid), demoforge.create_workspace(text) TO demoforge_api;

        GRANT SELECT, UPDATE (name) ON demoforge.workspaces TO demoforge_api;
        GRANT SELECT, INSERT, UPDATE (role), DELETE ON demoforge.memberships TO demoforge_api;

        CREATE POLICY workspace_read ON demoforge.workspaces FOR SELECT TO demoforge_api
            USING (demoforge.workspace_role(id) IS NOT NULL);
        CREATE POLICY workspace_rename ON demoforge.workspaces FOR UPDATE TO demoforge_api
            USING (demoforge.workspace_role(id) = 'admin')
            WITH CHECK (demoforge.workspace_role(id) = 'admin');

        CREATE POLICY membership_read ON demoforge.memberships FOR SELECT TO demoforge_api
            USING (
                user_id = demoforge.request_subject()
                OR demoforge.workspace_role(workspace_id) = 'admin'
            );
        CREATE POLICY membership_add ON demoforge.memberships FOR INSERT TO demoforge_api
            WITH CHECK (role <> 'admin' AND demoforge.workspace_role(workspace_id) = 'admin');
        CREATE POLICY membership_change ON demoforge.memberships FOR UPDATE TO demoforge_api
            USING (role <> 'admin' AND demoforge.workspace_role(workspace_id) = 'admin')
            WITH CHECK (role <> 'admin' AND demoforge.workspace_role(workspace_id) = 'admin');
        CREATE POLICY membership_remove ON demoforge.memberships FOR DELETE TO demoforge_api
            USING (role <> 'admin' AND demoforge.workspace_role(workspace_id) = 'admin');
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION demoforge.create_workspace(text);
        DROP TABLE demoforge.memberships;
        DROP TABLE demoforge.workspaces;
        DROP FUNCTION demoforge.workspace_role(uuid);
        DROP FUNCTION demoforge.request_subject();
        DROP SCHEMA demoforge;
    """)
