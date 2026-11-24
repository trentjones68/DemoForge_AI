"""Private discovery originals, immutable source segments and import audit."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE demoforge.discovery_sessions (
            workspace_id uuid NOT NULL,
            opportunity_id uuid NOT NULL,
            id uuid NOT NULL,
            title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 120),
            occurred_on date,
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, id),
            FOREIGN KEY (workspace_id, opportunity_id)
                REFERENCES demoforge.opportunities(workspace_id, id)
        );
        CREATE INDEX discovery_opportunity_idx
            ON demoforge.discovery_sessions (workspace_id, opportunity_id, created_at, id);

        CREATE TABLE demoforge.source_documents (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('transcript', 'summary')),
            provider text NOT NULL CHECK (provider IN ('manual', 'plaud')),
            method text NOT NULL CHECK (method IN ('paste', 'file')),
            format text NOT NULL CHECK (format IN ('txt', 'md', 'docx', 'pdf')),
            filename text CHECK (char_length(filename) BETWEEN 1 AND 120),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            byte_count integer NOT NULL CHECK (byte_count BETWEEN 1 AND 2097152),
            consent_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            imported_by uuid NOT NULL DEFAULT demoforge.request_subject(),
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready')),
            PRIMARY KEY (workspace_id, session_id, id),
            UNIQUE (workspace_id, session_id, kind, sha256),
            CHECK (
                (method = 'paste' AND filename IS NULL AND format = 'txt')
                OR (method = 'file' AND filename IS NOT NULL)
            ),
            FOREIGN KEY (workspace_id, session_id)
                REFERENCES demoforge.discovery_sessions(workspace_id, id)
        );

        CREATE TABLE demoforge.transcript_segments (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            source_id uuid NOT NULL,
            id uuid NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 2999),
            start_offset integer NOT NULL CHECK (start_offset >= 0),
            end_offset integer NOT NULL CHECK (end_offset <= 250000),
            text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 4000),
            speaker text CHECK (char_length(speaker) BETWEEN 1 AND 64),
            start_ms bigint CHECK (start_ms >= 0),
            end_ms bigint CHECK (end_ms >= start_ms),
            PRIMARY KEY (workspace_id, session_id, source_id, id),
            UNIQUE (workspace_id, session_id, source_id, ordinal),
            CHECK (end_offset = start_offset + char_length(text)),
            FOREIGN KEY (workspace_id, session_id, source_id)
                REFERENCES demoforge.source_documents(workspace_id, session_id, id)
        );

        CREATE TABLE demoforge.discovery_audit_events (
            workspace_id uuid NOT NULL,
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            session_id uuid NOT NULL,
            source_id uuid,
            actor_id uuid,
            action text NOT NULL CHECK (action IN ('session_created', 'source_imported')),
            occurred_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            FOREIGN KEY (workspace_id, session_id)
                REFERENCES demoforge.discovery_sessions(workspace_id, id),
            FOREIGN KEY (workspace_id, session_id, source_id)
                REFERENCES demoforge.source_documents(workspace_id, session_id, id)
        );

        CREATE FUNCTION demoforge.can_write_discovery(target uuid, opportunity uuid)
        RETURNS boolean LANGUAGE sql STABLE SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM demoforge.opportunities o
                WHERE o.workspace_id = target AND o.id = opportunity
                    AND o.archived_at IS NULL
                    AND (demoforge.workspace_role(target) = 'admin'
                         OR (demoforge.workspace_role(target) = 'sales_engineer'
                             AND o.owner_id = demoforge.request_subject()))
            )
        $$;

        CREATE FUNCTION demoforge.can_write_discovery_source(target uuid, session uuid)
        RETURNS boolean LANGUAGE sql STABLE SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM demoforge.discovery_sessions d
                WHERE d.workspace_id = target AND d.id = session
                    AND demoforge.can_write_discovery(target, d.opportunity_id)
            )
        $$;

        CREATE FUNCTION demoforge.discovery_upload_has_capacity(
            target uuid, session uuid, incoming_bytes integer
        ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT demoforge.can_write_discovery_source(target, session)
                AND count(*) < 200
                AND count(*) FILTER (WHERE d.session_id = session) < 20
                AND coalesce(sum(d.byte_count), 0) + incoming_bytes <= 104857600
            FROM demoforge.source_documents d WHERE d.workspace_id = target
        $$;
        REVOKE ALL ON FUNCTION demoforge.discovery_upload_has_capacity(uuid, uuid, integer)
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION demoforge.discovery_upload_has_capacity(uuid, uuid, integer)
            TO demoforge_api;

        CREATE FUNCTION demoforge.record_discovery_change() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        BEGIN
            IF TG_TABLE_NAME = 'discovery_sessions' THEN
                INSERT INTO demoforge.discovery_audit_events
                    (workspace_id, session_id, actor_id, action)
                VALUES (NEW.workspace_id, NEW.id, demoforge.request_subject(), 'session_created');
            ELSE
                INSERT INTO demoforge.discovery_audit_events
                    (workspace_id, session_id, source_id, actor_id, action)
                VALUES (NEW.workspace_id, NEW.session_id, NEW.id,
                    demoforge.request_subject(), 'source_imported');
            END IF;
            RETURN NULL;
        END
        $$;
        REVOKE ALL ON FUNCTION demoforge.can_write_discovery(uuid, uuid),
            demoforge.can_write_discovery_source(uuid, uuid),
            demoforge.record_discovery_change() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION demoforge.can_write_discovery(uuid, uuid),
            demoforge.can_write_discovery_source(uuid, uuid) TO demoforge_api;
        CREATE TRIGGER discovery_session_audit AFTER INSERT ON demoforge.discovery_sessions
            FOR EACH ROW EXECUTE FUNCTION demoforge.record_discovery_change();
        CREATE TRIGGER discovery_source_audit AFTER UPDATE OF status ON demoforge.source_documents
            FOR EACH ROW WHEN (OLD.status = 'pending' AND NEW.status = 'ready')
            EXECUTE FUNCTION demoforge.record_discovery_change();

        ALTER TABLE demoforge.discovery_sessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE demoforge.source_documents ENABLE ROW LEVEL SECURITY;
        ALTER TABLE demoforge.transcript_segments ENABLE ROW LEVEL SECURITY;
        ALTER TABLE demoforge.discovery_audit_events ENABLE ROW LEVEL SECURITY;

        GRANT SELECT, INSERT (workspace_id, opportunity_id, id, title, occurred_on)
            ON demoforge.discovery_sessions TO demoforge_api;
        GRANT SELECT, INSERT (
            workspace_id, session_id, id, kind, provider, method, format, filename, sha256,
            byte_count
        ), UPDATE (status) ON demoforge.source_documents TO demoforge_api;
        GRANT SELECT, INSERT ON demoforge.transcript_segments TO demoforge_api;
        GRANT SELECT ON demoforge.discovery_audit_events TO demoforge_api;

        CREATE POLICY discovery_session_read ON demoforge.discovery_sessions
            FOR SELECT TO demoforge_api
            USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer'));
        CREATE POLICY discovery_session_create ON demoforge.discovery_sessions
            FOR INSERT TO demoforge_api
            WITH CHECK (demoforge.can_write_discovery(workspace_id, opportunity_id));

        CREATE POLICY discovery_source_read ON demoforge.source_documents
            FOR SELECT TO demoforge_api
            USING (demoforge.workspace_role(workspace_id) IN ('admin', 'sales_engineer')
                AND (status = 'ready' OR demoforge.can_write_discovery_source(
                    workspace_id, session_id
                )));
        CREATE POLICY discovery_source_create ON demoforge.source_documents
            FOR INSERT TO demoforge_api
            WITH CHECK (status = 'pending'
                AND demoforge.can_write_discovery_source(workspace_id, session_id));
        CREATE POLICY discovery_source_complete ON demoforge.source_documents
            FOR UPDATE TO demoforge_api
            USING (status = 'pending'
                AND demoforge.can_write_discovery_source(workspace_id, session_id))
            WITH CHECK (status = 'ready'
                AND demoforge.can_write_discovery_source(workspace_id, session_id));

        CREATE POLICY discovery_segment_read ON demoforge.transcript_segments
            FOR SELECT TO demoforge_api USING (
                EXISTS (
                    SELECT FROM demoforge.source_documents d
                    WHERE d.workspace_id = transcript_segments.workspace_id
                        AND d.session_id = transcript_segments.session_id
                        AND d.id = transcript_segments.source_id
                        AND d.status = 'ready'
                )
            );
        CREATE POLICY discovery_segment_create ON demoforge.transcript_segments
            FOR INSERT TO demoforge_api WITH CHECK (
                demoforge.can_write_discovery_source(workspace_id, session_id)
                AND EXISTS (
                    SELECT FROM demoforge.source_documents d
                    WHERE d.workspace_id = transcript_segments.workspace_id
                        AND d.session_id = transcript_segments.session_id
                        AND d.id = transcript_segments.source_id
                        AND d.status = 'pending'
                )
            );
        CREATE POLICY discovery_audit_read ON demoforge.discovery_audit_events
            FOR SELECT TO demoforge_api USING (demoforge.workspace_role(workspace_id) = 'admin');

        INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
        VALUES ('discovery-originals', 'discovery-originals', false, 2097152,
                ARRAY['text/plain', 'text/markdown', 'application/pdf',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document']);
        CREATE POLICY discovery_originals_server_only ON storage.objects
            AS RESTRICTIVE FOR ALL TO anon, authenticated
            USING (bucket_id <> 'discovery-originals')
            WITH CHECK (bucket_id <> 'discovery-originals');
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM storage.buckets WHERE id = 'discovery-originals') THEN
                RAISE EXCEPTION
                    'Back up originals, then empty and delete discovery-originals via Storage API';
            END IF;
        END
        $$;
        DROP POLICY discovery_originals_server_only ON storage.objects;
        DROP FUNCTION demoforge.discovery_upload_has_capacity(uuid, uuid, integer);
        DROP TABLE demoforge.discovery_audit_events;
        DROP TABLE demoforge.transcript_segments;
        DROP TABLE demoforge.source_documents;
        DROP FUNCTION demoforge.can_write_discovery_source(uuid, uuid);
        DROP TABLE demoforge.discovery_sessions;
        DROP FUNCTION demoforge.can_write_discovery(uuid, uuid);
        DROP FUNCTION demoforge.record_discovery_change();
    """)
