from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import create_engine, text


def _plan_uses_index(node: Mapping[str, Any], index_name: str) -> bool:
    if node.get("Index Name") == index_name:
        return True
    plans = node.get("Plans")
    return isinstance(plans, Sequence) and any(
        isinstance(child, Mapping) and _plan_uses_index(child, index_name) for child in plans
    )


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL is required for the PostgreSQL planner integration test",
)
def test_postgres_lexical_match_uses_gin_index() -> None:
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    index_name = "ix_retrieval_fts_probe"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TEMP TABLE retrieval_fts_probe (
                    id bigint GENERATED ALWAYS AS IDENTITY,
                    workspace_id uuid NOT NULL,
                    episode_id uuid NOT NULL,
                    text text NOT NULL
                ) ON COMMIT DROP
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO retrieval_fts_probe (workspace_id, episode_id, text)
                SELECT
                    '00000000-0000-0000-0000-000000000001'::uuid,
                    '00000000-0000-0000-0000-000000000002'::uuid,
                    CASE WHEN value % 100 = 0
                        THEN 'needle podcast retrieval'
                        ELSE 'unrelated transcript content'
                    END
                FROM generate_series(1, 10000) AS value
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE INDEX {index_name}
                ON retrieval_fts_probe
                USING gin (to_tsvector('simple', text))
                """
            )
        )
        connection.execute(text("ANALYZE retrieval_fts_probe"))
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        count = connection.scalar(
            text(
                """
                SELECT count(*)
                FROM retrieval_fts_probe
                WHERE workspace_id = '00000000-0000-0000-0000-000000000001'::uuid
                  AND episode_id = '00000000-0000-0000-0000-000000000002'::uuid
                  AND to_tsvector('simple'::regconfig, text)
                      @@ websearch_to_tsquery('simple'::regconfig, 'needle')
                """
            )
        )
        plan = connection.scalar(
            text(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT id
                FROM retrieval_fts_probe
                WHERE workspace_id = '00000000-0000-0000-0000-000000000001'::uuid
                  AND episode_id = '00000000-0000-0000-0000-000000000002'::uuid
                  AND to_tsvector('simple'::regconfig, text)
                      @@ websearch_to_tsquery('simple'::regconfig, 'needle')
                """
            )
        )

    engine.dispose()
    assert count == 100
    assert isinstance(plan, list)
    assert _plan_uses_index(plan[0]["Plan"], index_name)
