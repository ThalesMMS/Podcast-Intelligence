"""Add the durable processing-job dispatch outbox.

Revision ID: 0003_job_dispatch_outbox
Revises: 0002_transcript_lookup_index
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_dispatch_outbox"
down_revision: str | None = "0002_transcript_lookup_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_dispatches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_job_dispatch_job"),
    )
    op.create_index(
        "ix_job_dispatch_pending",
        "job_dispatches",
        ["dispatched_at", "available_at"],
    )
    op.execute(
        """
        INSERT INTO job_dispatches (
            id,
            job_id,
            attempts,
            available_at,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            id,
            0,
            now(),
            now(),
            now()
        FROM processing_jobs
        WHERE status IN ('QUEUED', 'RETRYING', 'queued', 'retrying')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_job_dispatch_pending", table_name="job_dispatches")
    op.drop_table("job_dispatches")
