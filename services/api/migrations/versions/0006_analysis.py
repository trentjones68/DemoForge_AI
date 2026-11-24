"""Durable discovery analysis, pinned evidence, and revision approval."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE demoforge.analysis_jobs (
            workspace_id uuid NOT NULL,
            session_id uuid NOT NULL,
            id uuid NOT NULL UNIQUE,
            requested_by uuid NOT NULL DEFAULT demoforge.request_subject(),
            input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
            provider text NOT NULL CHECK (provider IN ('openai', 'fake')),
            model text NOT NULL,
            prompt_version text NOT NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','succeeded','failed')),
            attempts int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
            error_code text CHECK (error_code IN (
                'input_limit','invalid_output','provider_unavailable',
                'provider_rejected','access_revoked','worker_interrupted','configuration_changed'
            )),
            lease uuid,
            lease_until timestamptz,
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            available_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, session_id, id),
            FOREIGN KEY (workspace_id, session_id)
                REFERENCES demoforge.discovery_sessions(workspace_id, id),
            UNIQUE (workspace_id, session_id, input_hash, provider, model, prompt_version),
            CHECK ((status = 'running') = (lease IS NOT NULL AND lease_until IS NOT NULL))
        );
        CREATE INDEX analysis_queue_idx
            ON demoforge.analysis_jobs(available_at, created_at, id)
            WHERE status IN ('queued','running');
        CREATE INDEX analysis_workspace_created_idx
            ON demoforge.analysis_jobs(workspace_id, created_at);
        CREATE UNIQUE INDEX analysis_one_active_session
            ON demoforge.analysis_jobs(workspace_id, session_id)
            WHERE status IN ('queued','running');

        CREATE TABLE demoforge.analysis_sources (
            workspace_id uuid NOT NULL, session_id uuid NOT NULL,
            job_id uuid NOT NULL, source_id uuid NOT NULL,
            PRIMARY KEY (workspace_id, session_id, job_id, source_id),
            FOREIGN KEY (workspace_id, session_id, job_id)
                REFERENCES demoforge.analysis_jobs(workspace_id, session_id, id),
            FOREIGN KEY (workspace_id, session_id, source_id)
                REFERENCES demoforge.source_documents(workspace_id, session_id, id)
        );
        CREATE TABLE demoforge.analysis_findings (
            workspace_id uuid NOT NULL, session_id uuid NOT NULL,
            job_id uuid NOT NULL, id uuid NOT NULL,
            revision int NOT NULL CHECK (revision BETWEEN 1 AND 2147483646),
            kind text NOT NULL CHECK (kind IN (
                'pain_point','goal','requirement','persona','integration','objection',
                'metric','constraint','success_criterion','unknown'
            )),
            classification text NOT NULL CHECK (
                classification IN ('direct','inference','unknown','contradictory')
            ),
            statement text NOT NULL CHECK (char_length(btrim(statement)) BETWEEN 1 AND 800),
            rationale text NOT NULL CHECK (char_length(btrim(rationale)) BETWEEN 1 AND 800),
            confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
            editor_id uuid,
            created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, session_id, job_id, id, revision),
            FOREIGN KEY (workspace_id, session_id, job_id)
                REFERENCES demoforge.analysis_jobs(workspace_id, session_id, id),
            CHECK ((revision = 1) = (editor_id IS NULL)),
            CHECK ((kind = 'unknown') = (classification = 'unknown'))
        );
        CREATE TABLE demoforge.analysis_citations (
            workspace_id uuid NOT NULL, session_id uuid NOT NULL, job_id uuid NOT NULL,
            finding_id uuid NOT NULL, revision int NOT NULL,
            source_id uuid NOT NULL, segment_id uuid NOT NULL,
            quote_start int NOT NULL CHECK (quote_start >= 0),
            quote_end int NOT NULL CHECK (quote_end > quote_start AND quote_end <= 4000),
            PRIMARY KEY (workspace_id, session_id, job_id, finding_id, revision,
                         segment_id, quote_start),
            FOREIGN KEY (workspace_id, session_id, job_id, finding_id, revision)
                REFERENCES demoforge.analysis_findings
                    (workspace_id, session_id, job_id, id, revision),
            FOREIGN KEY (workspace_id, session_id, job_id, source_id)
                REFERENCES demoforge.analysis_sources(workspace_id, session_id, job_id, source_id),
            FOREIGN KEY (workspace_id, session_id, source_id, segment_id)
                REFERENCES demoforge.transcript_segments(workspace_id, session_id, source_id, id)
        );
        CREATE TABLE demoforge.analysis_approvals (
            workspace_id uuid NOT NULL, session_id uuid NOT NULL, job_id uuid NOT NULL,
            finding_id uuid NOT NULL, revision int NOT NULL,
            actor_id uuid NOT NULL DEFAULT demoforge.request_subject(),
            approved_at timestamptz NOT NULL DEFAULT statement_timestamp(),
            PRIMARY KEY (workspace_id, session_id, job_id, finding_id, revision),
            FOREIGN KEY (workspace_id, session_id, job_id, finding_id, revision)
                REFERENCES demoforge.analysis_findings
                    (workspace_id, session_id, job_id, id, revision)
        );
    """)
    add_request_policies()
    add_worker_functions()


def add_request_policies() -> None:
    # Names below are a fixed migration constant.
    for table in (
        "analysis_jobs",
        "analysis_sources",
        "analysis_findings",
        "analysis_citations",
        "analysis_approvals",
    ):
        op.execute(f"""
            ALTER TABLE demoforge.{table} ENABLE ROW LEVEL SECURITY;
            GRANT SELECT ON demoforge.{table} TO demoforge_api;
            CREATE POLICY analysis_read ON demoforge.{table} FOR SELECT TO demoforge_api
                USING (demoforge.workspace_role(workspace_id) IN ('admin','sales_engineer'));
        """)
    op.execute("""
        GRANT INSERT (workspace_id, session_id, id, input_hash, provider, model, prompt_version)
            ON demoforge.analysis_jobs TO demoforge_api;
        GRANT INSERT ON demoforge.analysis_sources, demoforge.analysis_citations TO demoforge_api;
        GRANT INSERT (
            workspace_id, session_id, job_id, id, revision, kind, classification, statement,
            rationale, confidence, editor_id
        ) ON demoforge.analysis_findings TO demoforge_api;
        GRANT INSERT (workspace_id, session_id, job_id, finding_id, revision)
            ON demoforge.analysis_approvals TO demoforge_api;

        CREATE POLICY analysis_enqueue ON demoforge.analysis_jobs FOR INSERT TO demoforge_api
            WITH CHECK (
                requested_by = demoforge.request_subject()
                AND demoforge.can_write_discovery_source(workspace_id, session_id)
            );
        CREATE POLICY analysis_snapshot ON demoforge.analysis_sources FOR INSERT TO demoforge_api
            WITH CHECK (
                demoforge.can_write_discovery_source(workspace_id, session_id)
                AND EXISTS (
                    SELECT FROM demoforge.analysis_jobs j
                    WHERE j.workspace_id = analysis_sources.workspace_id
                      AND j.session_id = analysis_sources.session_id AND j.id = job_id
                      AND j.status = 'queued' AND j.attempts = 0
                      AND j.requested_by = demoforge.request_subject()
                )
                AND EXISTS (
                    SELECT FROM demoforge.source_documents d
                    WHERE d.workspace_id = analysis_sources.workspace_id
                      AND d.session_id = analysis_sources.session_id AND d.id = source_id
                      AND d.kind = 'transcript' AND d.status = 'ready'
                )
            );
        CREATE POLICY analysis_edit ON demoforge.analysis_findings FOR INSERT TO demoforge_api
            WITH CHECK (
                revision > 1 AND editor_id = demoforge.request_subject()
                AND demoforge.can_write_discovery_source(workspace_id, session_id)
            );
        CREATE POLICY analysis_copy_evidence ON demoforge.analysis_citations
            FOR INSERT TO demoforge_api
            WITH CHECK (
                revision > 1 AND demoforge.can_write_discovery_source(workspace_id, session_id)
            );
        CREATE POLICY analysis_approve ON demoforge.analysis_approvals FOR INSERT TO demoforge_api
            WITH CHECK (
                actor_id = demoforge.request_subject()
                AND demoforge.can_write_discovery_source(workspace_id, session_id)
            );
    """)


def add_worker_functions() -> None:
    op.execute("""
        CREATE FUNCTION demoforge.analysis_actor_allowed(
            workspace uuid, session uuid, actor uuid
        ) RETURNS boolean LANGUAGE sql STABLE SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM demoforge.discovery_sessions d
                JOIN demoforge.opportunities o
                  ON o.workspace_id = d.workspace_id AND o.id = d.opportunity_id
                JOIN demoforge.memberships m
                  ON m.workspace_id = d.workspace_id AND m.user_id = actor
                WHERE d.workspace_id = workspace AND d.id = session AND o.archived_at IS NULL
                  AND (m.role = 'admin' OR (m.role = 'sales_engineer' AND o.owner_id = actor))
            )
        $$;

        CREATE FUNCTION demoforge.claim_analysis()
        RETURNS TABLE(job_id uuid, lease uuid, provider text, model text, prompt_version text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        BEGIN
            WITH expired AS (
                SELECT j.id FROM demoforge.analysis_jobs j
                WHERE j.status = 'running' AND j.lease_until <= statement_timestamp()
                  AND j.attempts = 3
                LIMIT 10 FOR UPDATE SKIP LOCKED
            )
            UPDATE demoforge.analysis_jobs j
            SET status = 'failed', error_code = 'worker_interrupted',
                lease = NULL, lease_until = NULL
            FROM expired WHERE j.id = expired.id;

            RETURN QUERY
            WITH next_job AS (
                SELECT j.id FROM demoforge.analysis_jobs j
                WHERE j.attempts < 3 AND (
                    (j.status = 'queued' AND j.available_at <= statement_timestamp())
                    OR (j.status = 'running' AND j.lease_until <= statement_timestamp())
                )
                ORDER BY j.available_at, j.created_at, j.id
                LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE demoforge.analysis_jobs j
            SET status = 'running', lease = gen_random_uuid(), error_code = NULL,
                lease_until = statement_timestamp() + interval '75 seconds',
                attempts = j.attempts + 1
            FROM next_job WHERE j.id = next_job.id
            RETURNING j.id, j.lease, j.provider, j.model, j.prompt_version;
        END
        $$;

        CREATE FUNCTION demoforge.analysis_worker_segments(job uuid, claim uuid)
        RETURNS TABLE(id uuid, text text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT s.id, s.text FROM demoforge.analysis_jobs j
            JOIN demoforge.analysis_sources a
              ON (a.workspace_id, a.session_id, a.job_id) = (j.workspace_id, j.session_id, j.id)
            JOIN demoforge.transcript_segments s
              ON (s.workspace_id, s.session_id, s.source_id) =
                 (a.workspace_id, a.session_id, a.source_id)
            WHERE j.id = job AND j.lease = claim AND j.status = 'running'
              AND j.lease_until > statement_timestamp()
              AND demoforge.analysis_actor_allowed(j.workspace_id, j.session_id, j.requested_by)
            ORDER BY a.source_id, s.ordinal
            LIMIT 601
        $$;

        CREATE FUNCTION demoforge.fail_analysis(job uuid, claim uuid, code text, retryable boolean)
        RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = ''
        AS $$
            WITH changed AS (
                UPDATE demoforge.analysis_jobs j
                SET status = CASE WHEN retryable AND j.attempts < 3 THEN 'queued' ELSE 'failed' END,
                    available_at = statement_timestamp() + (j.attempts * interval '10 seconds'),
                    error_code = code, lease = NULL, lease_until = NULL
                WHERE j.id = job AND j.lease = claim AND j.status = 'running'
                  AND j.lease_until > statement_timestamp()
                RETURNING j.id
            )
            SELECT EXISTS (SELECT FROM changed)
        $$;

        CREATE FUNCTION demoforge.complete_analysis(job uuid, claim uuid, findings jsonb)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE
            context demoforge.analysis_jobs%ROWTYPE;
            finding jsonb;
            finding_id uuid;
            inserted_count integer;
        BEGIN
            SELECT j.* INTO context FROM demoforge.analysis_jobs j
            WHERE j.id = job AND j.lease = claim AND j.status = 'running'
              AND j.lease_until > statement_timestamp()
            FOR UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;
            IF NOT demoforge.analysis_actor_allowed(
                context.workspace_id, context.session_id, context.requested_by
            ) THEN
                PERFORM demoforge.fail_analysis(job, claim, 'access_revoked', false);
                RETURN false;
            END IF;

            IF jsonb_array_length(findings) > 25 THEN
                RAISE EXCEPTION 'Invalid verified findings';
            END IF;
            FOR finding IN SELECT value FROM jsonb_array_elements(findings) LOOP
                finding_id := gen_random_uuid();
                INSERT INTO demoforge.analysis_findings (
                    workspace_id, session_id, job_id, id, revision, kind, classification,
                    statement, rationale, confidence
                ) VALUES (
                    context.workspace_id, context.session_id, job, finding_id, 1,
                    finding->>'kind', finding->>'classification', finding->>'statement',
                    finding->>'rationale', (finding->>'confidence')::double precision
                );
                INSERT INTO demoforge.analysis_citations (
                    workspace_id, session_id, job_id, finding_id, revision,
                    source_id, segment_id, quote_start, quote_end
                )
                SELECT context.workspace_id, context.session_id, job, finding_id, 1,
                       s.source_id, s.id, c.quote_start, c.quote_end
                FROM jsonb_to_recordset(finding->'evidence')
                     AS c(segment_id uuid, quote_start int, quote_end int)
                JOIN demoforge.transcript_segments s
                  ON s.workspace_id = context.workspace_id AND s.session_id = context.session_id
                     AND s.id = c.segment_id
                JOIN demoforge.analysis_sources a
                  ON (a.workspace_id, a.session_id, a.job_id, a.source_id) =
                     (context.workspace_id, context.session_id, job, s.source_id)
                WHERE c.quote_end <= char_length(s.text);
                GET DIAGNOSTICS inserted_count = ROW_COUNT;
                IF inserted_count <> jsonb_array_length(finding->'evidence')
                    OR (finding->>'classification' <> 'unknown' AND inserted_count < 1)
                    OR (finding->>'classification' = 'contradictory' AND inserted_count < 2)
                    OR inserted_count > 6 THEN
                    RAISE EXCEPTION 'Invalid verified evidence';
                END IF;
            END LOOP;

            UPDATE demoforge.analysis_jobs
            SET status = 'succeeded', lease = NULL, lease_until = NULL, error_code = NULL
            WHERE id = job;
            RETURN true;
        END
        $$;

        REVOKE ALL ON FUNCTION demoforge.analysis_actor_allowed(uuid, uuid, uuid),
            demoforge.claim_analysis(),
            demoforge.analysis_worker_segments(uuid, uuid),
            demoforge.fail_analysis(uuid, uuid, text, boolean),
            demoforge.complete_analysis(uuid, uuid, jsonb) FROM PUBLIC;
        GRANT USAGE ON SCHEMA demoforge TO demoforge_worker;
        GRANT EXECUTE ON FUNCTION demoforge.claim_analysis(),
            demoforge.analysis_worker_segments(uuid, uuid),
            demoforge.fail_analysis(uuid, uuid, text, boolean),
            demoforge.complete_analysis(uuid, uuid, jsonb) TO demoforge_worker;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION demoforge.complete_analysis(uuid, uuid, jsonb);
        DROP FUNCTION demoforge.fail_analysis(uuid, uuid, text, boolean);
        DROP FUNCTION demoforge.analysis_worker_segments(uuid, uuid);
        DROP FUNCTION demoforge.claim_analysis();
        DROP FUNCTION demoforge.analysis_actor_allowed(uuid, uuid, uuid);
        REVOKE USAGE ON SCHEMA demoforge FROM demoforge_worker;
        DROP TABLE demoforge.analysis_approvals, demoforge.analysis_citations,
            demoforge.analysis_findings, demoforge.analysis_sources, demoforge.analysis_jobs;
    """)
