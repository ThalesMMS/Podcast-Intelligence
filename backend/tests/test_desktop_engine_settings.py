from __future__ import annotations

import json
import os

from podcast_intelligence.desktop.engine import _load_user_settings


def test_packaged_engine_loads_provider_specific_base_urls(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "openai_transcription_base_url": "http://transcription.test/v1",
                "openai_embedding_base_url": "http://embedding.test/v1",
                "openai_llm_base_url": "http://llm.test/v1",
            }
        ),
        encoding="utf-8",
    )
    environment_names = {
        "OPENAI_TRANSCRIPTION_BASE_URL": "http://transcription.test/v1",
        "OPENAI_EMBEDDING_BASE_URL": "http://embedding.test/v1",
        "OPENAI_LLM_BASE_URL": "http://llm.test/v1",
    }
    for name in environment_names:
        monkeypatch.setenv(name, "")

    _load_user_settings(settings_path)

    assert {name: os.environ.get(name) for name in environment_names} == environment_names
