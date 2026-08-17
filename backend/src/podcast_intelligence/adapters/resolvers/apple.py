from __future__ import annotations

import re
from html.parser import HTMLParser

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.adapters.resolvers.rss import RSSResolver
from podcast_intelligence.domain.errors import SourceResolutionError
from podcast_intelligence.domain.types import ResolvedEpisode

_SHOW_ID_RE = re.compile(r"/id(\d+)")
_EPISODE_ID_RE = re.compile(r"[?&]i=(\d+)")


class _OpenGraphTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta" or self.title is not None:
            return
        attributes = dict(attrs)
        if (attributes.get("property") or "").lower() != "og:title":
            return
        content = attributes.get("content")
        if content:
            self.title = content


class ApplePodcastResolver:
    source_type = "apple"

    def __init__(self, http: SafeHTTPClient, rss: RSSResolver) -> None:
        self.http = http
        self.rss = rss

    def _page_title(self, url: str) -> str | None:
        try:
            page = self.http.fetch_text(url, max_bytes=3 * 1024 * 1024)
        except Exception:
            return None
        parser = _OpenGraphTitleParser()
        parser.feed(page)
        if not parser.title:
            return None
        value = parser.title.strip()
        for suffix in (" - Apple Podcasts", " on Apple Podcasts"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
        return value or None

    def resolve(
        self,
        url: str,
        *,
        episode_guid: str | None = None,
        episode_title: str | None = None,
        rss_url_hint: str | None = None,
    ) -> ResolvedEpisode:
        show_match = _SHOW_ID_RE.search(url)
        if not show_match:
            raise SourceResolutionError("Apple Podcasts URL does not contain a show ID")
        show_id = show_match.group(1)
        episode_match = _EPISODE_ID_RE.search(url)
        apple_episode_id = episode_match.group(1) if episode_match else None

        if rss_url_hint:
            feed_url = rss_url_hint
        else:
            lookup = self.http.fetch_json(
                f"https://itunes.apple.com/lookup?id={show_id}&entity=podcast",
                max_bytes=2 * 1024 * 1024,
            )
            results = lookup.get("results") or []
            record = next((item for item in results if item.get("feedUrl")), None)
            if not record:
                raise SourceResolutionError("Apple catalog did not expose a public RSS feed")
            feed_url = str(record["feedUrl"])

        title_hint = episode_title
        if not title_hint and apple_episode_id and not episode_guid:
            title_hint = self._page_title(url)
            if not title_hint:
                raise SourceResolutionError(
                    "Apple episode title could not be resolved; "
                    "provide episode_title or episode_guid"
                )

        resolved = self.rss.resolve(
            feed_url,
            episode_guid=episode_guid,
            episode_title=title_hint,
        )
        resolved.source_type = self.source_type
        resolved.external_id = apple_episode_id or resolved.external_id
        resolved.canonical_url = url
        resolved.metadata.update({"apple_show_id": show_id, "apple_episode_id": apple_episode_id})
        return resolved
