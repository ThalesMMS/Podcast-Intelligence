from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote_plus

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.adapters.resolvers.common import title_similarity
from podcast_intelligence.adapters.resolvers.rss import RSSResolver
from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import SourceResolutionError
from podcast_intelligence.domain.types import ResolvedEpisode

_EPISODE_RE = re.compile(r"open\.spotify\.com/(?:intl-[^/]+/)?episode/([A-Za-z0-9]+)")


class SpotifyPodcastResolver:
    source_type = "spotify"

    def __init__(self, settings: Settings, http: SafeHTTPClient, rss: RSSResolver) -> None:
        self.settings = settings
        self.http = http
        self.rss = rss

    def _metadata_with_client_credentials(self, episode_id: str) -> dict[str, Any] | None:
        if not (self.settings.spotify_client_id and self.settings.spotify_client_secret):
            return None
        raw = f"{self.settings.spotify_client_id}:{self.settings.spotify_client_secret}".encode()
        token_payload = self.http.post_form_json(
            "https://accounts.spotify.com/api/token",
            {"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {base64.b64encode(raw).decode()}"},
        )
        token = token_payload.get("access_token")
        if not token:
            return None
        response = self.http._request_with_redirects(
            "GET",
            f"https://api.spotify.com/v1/episodes/{episode_id}?market=US",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            if response.status_code >= 400:
                return None
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        finally:
            response.close()

    def _metadata_with_oembed(self, url: str) -> dict[str, Any]:
        return self.http.fetch_json(
            f"https://open.spotify.com/oembed?url={quote_plus(url)}",
            max_bytes=2 * 1024 * 1024,
        )

    def _discover_feed(self, show_name: str, publisher: str | None) -> str:
        term = " ".join(part for part in (show_name, publisher) if part)
        result = self.http.fetch_json(
            "https://itunes.apple.com/search?media=podcast&entity=podcast&limit=20&term="
            + quote_plus(term),
            max_bytes=4 * 1024 * 1024,
        )
        candidates = [item for item in result.get("results") or [] if item.get("feedUrl")]
        if not candidates:
            raise SourceResolutionError(
                "No public RSS feed could be discovered for this Spotify episode"
            )
        ranked = sorted(
            (
                (
                    title_similarity(show_name, str(item.get("collectionName") or "")),
                    item,
                )
                for item in candidates
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        score, best = ranked[0]
        if score < 0.45:
            raise SourceResolutionError(
                "Spotify metadata could not be matched confidently to a public RSS feed"
            )
        return str(best["feedUrl"])

    def resolve(
        self,
        url: str,
        *,
        episode_guid: str | None = None,
        episode_title: str | None = None,
        rss_url_hint: str | None = None,
    ) -> ResolvedEpisode:
        match = _EPISODE_RE.search(url)
        if not match:
            raise SourceResolutionError("Spotify URL does not contain an episode ID")
        episode_id = match.group(1)

        metadata = self._metadata_with_client_credentials(episode_id)
        if metadata:
            title = episode_title or str(metadata.get("name") or "")
            show = metadata.get("show") or {}
            show_name = str(show.get("name") or "")
            publisher = show.get("publisher")
            duration_ms = metadata.get("duration_ms")
        else:
            oembed = self._metadata_with_oembed(url)
            title = episode_title or str(oembed.get("title") or "")
            show_name = str(oembed.get("author_name") or title)
            publisher = oembed.get("provider_name")
            duration_ms = None

        if not title:
            raise SourceResolutionError("Spotify metadata did not include an episode title")
        feed_url = rss_url_hint or self._discover_feed(show_name or title, publisher)
        resolved = self.rss.resolve(feed_url, episode_guid=episode_guid, episode_title=title)

        if duration_ms and resolved.duration_ms:
            difference = abs(int(duration_ms) - resolved.duration_ms)
            tolerance = max(120_000, int(duration_ms) * 0.08)
            if difference > tolerance and resolved.resolution_confidence < 0.8:
                raise SourceResolutionError(
                    "The best RSS title match has a conflicting duration; provide rss_url_hint"
                )

        resolved.source_type = self.source_type
        resolved.external_id = episode_id
        resolved.canonical_url = url
        resolved.metadata.update(
            {
                "spotify_episode_id": episode_id,
                "spotify_show_name": show_name,
                "spotify_metadata_available": bool(metadata),
                "media_origin": "rss_enclosure",
            }
        )
        return resolved
