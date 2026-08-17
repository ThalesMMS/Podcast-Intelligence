"""Add terminal dead-letter state to durable job dispatches.

Revision ID: 0005_job_dispatch_dead_letter
Revises: 0004_job_episode_created_index
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_job_dispatch_dead_letter"
down_revision: str | None = "0004_job_episode_created_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_dispatches",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_job_dispatch_pending",
            table_name="job_dispatches",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_job_dispatch_pending",
            "job_dispatches",
            ["dispatched_at", "dead_lettered_at", "available_at"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_job_dispatch_pending",
            table_name="job_dispatches",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_job_dispatch_pending",
            "job_dispatches",
            ["dispatched_at", "available_at"],
            postgresql_concurrently=True,
        )
    op.drop_column("job_dispatches", "dead_lettered_at")
