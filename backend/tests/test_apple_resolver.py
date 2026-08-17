from __future__ import annotations

from unittest.mock import Mock

import pytest

from podcast_intelligence.adapters.resolvers.apple import ApplePodcastResolver
from podcast_intelligence.domain.errors import SourceResolutionError
from podcast_intelligence.domain.types import ResolvedEpisode

APPLE_EPISODE_URL = "https://podcasts.apple.com/us/podcast/example/id123?i=456"
APPLE_SHOW_URL = "https://podcasts.apple.com/us/podcast/example/id123"
RSS_URL = "https://example.com/feed.xml"


def _resolved_episode() -> ResolvedEpisode:
    return ResolvedEpisode(
        source_type="rss",
        external_id="rss-guid",
        canonical_url="https://example.com/episodes/target",
        rss_url=RSS_URL,
        media_url="https://example.com/target.mp3",
        title="Target Episode",
    )


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (
            '<meta property="og:title" content="Tom &amp; Jerry on Apple Podcasts">',
            "Tom & Jerry",
        ),
        (
            "<meta content='Tom &amp; Jerry on Apple Podcasts' property='og:title'>",
            "Tom & Jerry",
        ),
        (
            '<meta property="og:title" content="Research &amp;amp; Practice on Apple Podcasts">',
            "Research &amp; Practice",
        ),
    ],
)
def test_page_title_accepts_attribute_order_and_decodes_once(page: str, expected: str) -> None:
    http = Mock()
    http.fetch_text.return_value = page
    resolver = ApplePodcastResolver(http, Mock())

    assert resolver._page_title(APPLE_EPISODE_URL) == expected


def test_episode_url_passes_recovered_title_to_rss_resolver() -> None:
    http = Mock()
    http.fetch_text.return_value = (
        '<meta content="Target Episode - Apple Podcasts" property="og:title">'
    )
    rss = Mock()
    rss.resolve.return_value = _resolved_episode()

    resolved = ApplePodcastResolver(http, rss).resolve(
        APPLE_EPISODE_URL,
        rss_url_hint=RSS_URL,
    )

    rss.resolve.assert_called_once_with(
        RSS_URL,
        episode_guid=None,
        episode_title="Target Episode",
    )
    assert resolved.source_type == "apple"
    assert resolved.external_id == "456"
    assert resolved.canonical_url == APPLE_EPISODE_URL


def test_episode_url_fails_closed_when_title_is_unavailable() -> None:
    http = Mock()
    http.fetch_text.side_effect = RuntimeError("page unavailable")
    rss = Mock()

    with pytest.raises(SourceResolutionError, match="provide episode_title or episode_guid"):
        ApplePodcastResolver(http, rss).resolve(
            APPLE_EPISODE_URL,
            rss_url_hint=RSS_URL,
        )

    rss.resolve.assert_not_called()


def test_show_url_keeps_latest_episode_fallback() -> None:
    rss = Mock()
    rss.resolve.return_value = _resolved_episode()

    ApplePodcastResolver(Mock(), rss).resolve(
        APPLE_SHOW_URL,
        rss_url_hint=RSS_URL,
    )

    rss.resolve.assert_called_once_with(
        RSS_URL,
        episode_guid=None,
        episode_title=None,
    )
