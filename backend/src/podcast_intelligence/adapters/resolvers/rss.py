from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import feedparser

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.adapters.resolvers.common import (
    clean_html,
    parse_datetime,
    parse_duration_ms,
    select_artwork,
    select_enclosure,
    title_similarity,
    transcript_references,
)
from podcast_intelligence.domain.errors import SourceResolutionError
from podcast_intelligence.domain.types import ResolvedEpisode


class RSSResolver:
    source_type = "rss"

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
        feed_text = self.http.fetch_text(rss_url_hint or url, max_bytes=20 * 1024 * 1024)
        return self.resolve_feed_text(
            feed_text,
            rss_url=rss_url_hint or url,
            episode_guid=episode_guid,
            episode_title=episode_title,
        )

    def resolve_feed_text(
        self,
        feed_text: str,
        *,
        rss_url: str,
        episode_guid: str | None = None,
        episode_title: str | None = None,
    ) -> ResolvedEpisode:
        parsed = feedparser.parse(feed_text)
        if parsed.bozo and not parsed.entries:
            raise SourceResolutionError(f"Invalid RSS feed: {parsed.bozo_exception}")
        entries: list[dict[str, Any]] = list(parsed.entries)
        if not entries:
            raise SourceResolutionError("RSS feed contains no episodes")

        selected: dict[str, Any] | None = None
        confidence = 1.0
        if episode_guid:
            selected = next(
                (
                    entry
                    for entry in entries
                    if str(entry.get("id") or entry.get("guid") or "") == episode_guid
                ),
                None,
            )
            if selected is None:
                raise SourceResolutionError("Episode GUID was not found in the RSS feed")
        elif episode_title:
            ranked = sorted(
                (
                    (title_similarity(episode_title, str(entry.get("title") or "")), entry)
                    for entry in entries
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            confidence, selected = ranked[0]
            if confidence < 0.45:
                raise SourceResolutionError(
                    "Could not confidently match the requested episode title in the RSS feed"
                )
        else:
            selected = max(
                entries, key=lambda entry: parse_datetime(entry) or datetime.min.replace(tzinfo=UTC)
            )
            confidence = 0.75

        try:
            media_url, media_type = select_enclosure(selected)
        except ValueError as exc:
            raise SourceResolutionError(str(exc)) from exc

        feed = dict(parsed.feed)
        title = str(selected.get("title") or "Untitled episode")
        guid = str(selected.get("id") or selected.get("guid") or "") or None
        duration_ms = parse_duration_ms(selected.get("itunes_duration") or selected.get("duration"))

        return ResolvedEpisode(
            source_type=self.source_type,
            external_id=guid,
            canonical_url=str(selected.get("link") or rss_url),
            rss_url=rss_url,
            media_url=media_url,
            media_mime_type=media_type,
            title=title,
            description=clean_html(selected.get("summary") or selected.get("description")),
            published_at=parse_datetime(selected),
            duration_ms=duration_ms,
            language=selected.get("language") or feed.get("language"),
            artwork_url=select_artwork(selected) or select_artwork(feed),
            show_title=feed.get("title"),
            show_author=feed.get("author") or feed.get("itunes_author"),
            show_description=clean_html(feed.get("summary") or feed.get("description")),
            show_artwork_url=select_artwork(feed),
            published_transcripts=[
                reference.model_copy(update={"url": urljoin(rss_url, reference.url)})
                for reference in transcript_references(selected)
            ],
            resolution_confidence=confidence,
            metadata={
                "rss_guid": guid,
                "feed_link": feed.get("link"),
                "entry_links": selected.get("links") or [],
            },
        )
