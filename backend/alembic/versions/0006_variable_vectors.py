"""Allow embedding providers with different vector dimensions.

Revision ID: 0006_variable_vectors
Revises: 0005_job_dispatch_dead_letter
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006_variable_vectors"
down_revision: str | None = "0005_job_dispatch_dead_letter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(dim=1536),
        type_=Vector(),
        postgresql_using="embedding::vector",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM knowledge_chunks
                WHERE embedding IS NOT NULL
                  AND vector_dims(embedding) <> 1536
            ) THEN
                RAISE EXCEPTION
                    'Cannot restore vector(1536) while non-1536 embeddings exist';
            END IF;
        END
        $$;
        """
    )
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(),
        type_=Vector(dim=1536),
        postgresql_using="embedding::vector(1536)",
        existing_nullable=True,
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
