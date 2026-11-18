"""Establish the empty application migration baseline."""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the baseline. Application tables follow in later revisions."""


def downgrade() -> None:
    """Restore the empty revision history."""
