from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.domain.types import ResolvedEpisode


class DirectMediaResolver:
    source_type = "direct_url"

    def __init__(self, http: SafeHTTPClient) -> None:
        self.http = http

    def resolve(
        self,
        url: str,
        *,
        episode_guid: str | None = None,
        episode_title: str | None = None,
        rss_url_hint: str | None = None,
    ) -> ResolvedEpisode:
        validated = self.http.validate_url(url)
        path_name = PurePosixPath(unquote(urlsplit(validated).path)).name
        title = episode_title or path_name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        return ResolvedEpisode(
            source_type=self.source_type,
            external_id=episode_guid,
            canonical_url=validated,
            media_url=validated,
            title=title.strip() or "Imported audio",
            resolution_confidence=1.0,
        )
