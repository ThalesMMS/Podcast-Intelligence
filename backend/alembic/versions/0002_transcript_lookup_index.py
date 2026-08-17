"""Add the latest-transcript lookup index.

Revision ID: 0002_transcript_lookup_index
Revises: 0001_initial
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_transcript_lookup_index"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_transcripts_episode_status_version",
        "transcripts",
        ["episode_id", "status", sa.text("version DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcripts_episode_status_version",
        table_name="transcripts",
    )
