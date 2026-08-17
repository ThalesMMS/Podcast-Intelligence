from __future__ import annotations

from podcast_intelligence.domain.types import EpisodeSummaryDocument


def test_summary_schema_rejects_missing_required_fields() -> None:
    document = EpisodeSummaryDocument.model_validate(
        {
            "executive_summary": "Summary",
            "detailed_summary": "Details",
            "chapters": [],
            "key_takeaways": [],
        }
    )
    assert document.people == []
    assert document.topics == []
