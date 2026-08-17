"""Index processing jobs for latest-by-episode lookups.

Revision ID: 0004_job_episode_created_index
Revises: 0003_job_dispatch_outbox
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_job_episode_created_index"
down_revision: str | None = "0003_job_dispatch_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_job_episode_created",
            "processing_jobs",
            ["episode_id", "created_at", "updated_at"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_job_episode_created",
            table_name="processing_jobs",
            postgresql_concurrently=True,
        )
