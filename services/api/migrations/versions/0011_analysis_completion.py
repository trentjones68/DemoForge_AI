"""Record analysis terminal times for queue-inclusive duration and failure rate."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE demoforge.analysis_jobs ADD COLUMN completed_at timestamptz;
        CREATE INDEX analysis_workspace_completed_idx
            ON demoforge.analysis_jobs(workspace_id, completed_at)
            WHERE completed_at IS NOT NULL;

        CREATE FUNCTION demoforge.record_analysis_completion() RETURNS trigger
        LANGUAGE plpgsql SET search_path = '' AS $$
        BEGIN
            NEW.completed_at := CASE WHEN NEW.status IN ('succeeded', 'failed')
                THEN clock_timestamp() ELSE NULL END;
            RETURN NEW;
        END $$;
        REVOKE ALL ON FUNCTION demoforge.record_analysis_completion() FROM PUBLIC;
        CREATE TRIGGER analysis_completion BEFORE UPDATE OF status ON demoforge.analysis_jobs
            FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
            EXECUTE FUNCTION demoforge.record_analysis_completion();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER analysis_completion ON demoforge.analysis_jobs;
        DROP FUNCTION demoforge.record_analysis_completion();
        DROP INDEX demoforge.analysis_workspace_completed_idx;
        ALTER TABLE demoforge.analysis_jobs DROP COLUMN completed_at;
    """)
