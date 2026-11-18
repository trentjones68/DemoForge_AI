"""Private Supabase Storage scoped by workspace path."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_class
                WHERE oid = pg_catalog.to_regclass('storage.objects') AND relrowsecurity
            ) THEN
                RAISE EXCEPTION 'Revision 0003 requires Supabase Storage with RLS enabled';
            END IF;
        END
        $$;

        ALTER TABLE demoforge.memberships ADD CONSTRAINT memberships_auth_user_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

        INSERT INTO storage.buckets (id, name, public)
        VALUES ('workspace-files', 'workspace-files', false);

        CREATE FUNCTION demoforge.can_access_workspace_object(object_name text) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM demoforge.memberships m
                WHERE m.user_id = auth.uid()
                  AND m.role IN ('admin', 'sales_engineer')
                  AND (
                      nullif(current_setting('request.jwt.claims', true), '')::jsonb
                      ->> 'is_anonymous'
                  ) IS DISTINCT FROM 'true'
                  AND m.workspace_id = CASE
                      WHEN split_part(object_name, '/', 1)
                          ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                      AND strpos(object_name, '/') > 0
                      AND object_name !~ '(^|/)([.]{1,2})?(/|$)'
                      THEN split_part(object_name, '/', 1)::uuid
                  END
            )
        $$;

        REVOKE ALL ON FUNCTION demoforge.can_access_workspace_object(text) FROM PUBLIC;
        GRANT USAGE ON SCHEMA demoforge TO anon, authenticated;
        GRANT EXECUTE ON FUNCTION demoforge.can_access_workspace_object(text)
            TO anon, authenticated;

        -- A permissive policy from another app cannot override this workspace boundary.
        CREATE POLICY demoforge_workspace_boundary ON storage.objects
            AS RESTRICTIVE FOR ALL TO anon, authenticated
            USING (
                CASE WHEN bucket_id = 'workspace-files'
                    THEN demoforge.can_access_workspace_object(name) ELSE true END
            )
            WITH CHECK (
                CASE WHEN bucket_id = 'workspace-files'
                    THEN demoforge.can_access_workspace_object(name) ELSE true END
            );
        CREATE POLICY demoforge_workspace_objects ON storage.objects
            FOR ALL TO authenticated
            USING (bucket_id = 'workspace-files')
            WITH CHECK (bucket_id = 'workspace-files');
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM storage.buckets WHERE id = 'workspace-files') THEN
                RAISE EXCEPTION
                    'Empty and delete workspace-files using the Storage API before rollback';
            END IF;
        END
        $$;

        DROP POLICY demoforge_workspace_objects ON storage.objects;
        DROP POLICY demoforge_workspace_boundary ON storage.objects;

        DROP FUNCTION demoforge.can_access_workspace_object(text);
        REVOKE USAGE ON SCHEMA demoforge FROM anon, authenticated;

        ALTER TABLE demoforge.memberships DROP CONSTRAINT memberships_auth_user_fkey;
    """)
