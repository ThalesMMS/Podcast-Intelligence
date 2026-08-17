from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from podcast_intelligence.models import Summary
from podcast_intelligence.services.exports import summary_markdown


def test_summary_markdown_uses_english_headings_and_fallbacks() -> None:
    summary = cast(
        Summary,
        SimpleNamespace(
            content_json={
                "executive_summary": "Overview.",
                "detailed_summary": "Details.",
                "chapters": [{"start_ms": 0, "summary": "Opening."}],
                "key_takeaways": [{"text": "Keep evidence linked."}],
            }
        ),
    )

    output = summary_markdown("Episode", summary)

    assert "## Detailed summary" in output
    assert "## Chapters" in output
    assert "### 00:00:00 — Chapter" in output
    assert "## Key takeaways" in output
    for former_heading in ("Resumo detalhado", "Capítulos", "Capítulo", "Pontos principais"):
        assert former_heading not in output
