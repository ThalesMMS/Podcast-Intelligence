from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any

from podcast_intelligence.domain.types import TranscriptReference

_DURATION_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.\d+)?$")
_TAG_RE = re.compile(r"<[^>]+>")


def clean_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", value)).strip()


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def parse_duration_ms(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        return int(seconds * 1000) if seconds >= 0 else None
    text = str(value).strip()
    if text.isdigit():
        return int(text) * 1000
    match = _DURATION_RE.match(text)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def parse_datetime(entry: dict[str, Any]) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            result = parsedate_to_datetime(str(raw))
            return result if result.tzinfo else result.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    return None


def select_artwork(container: dict[str, Any]) -> str | None:
    image = container.get("image")
    if isinstance(image, dict) and image.get("href"):
        return str(image["href"])
    itunes_image = container.get("itunes_image")
    if isinstance(itunes_image, dict) and itunes_image.get("href"):
        return str(itunes_image["href"])
    if isinstance(itunes_image, str):
        return itunes_image
    return None


def select_enclosure(entry: dict[str, Any]) -> tuple[str, str | None]:
    enclosures = entry.get("enclosures") or []
    for enclosure in enclosures:
        href = enclosure.get("href") or enclosure.get("url")
        media_type = enclosure.get("type")
        if href and (not media_type or str(media_type).startswith(("audio/", "video/"))):
            return str(href), str(media_type) if media_type else None
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return str(link["href"]), link.get("type")
    raise ValueError("RSS item does not contain an audio/video enclosure")


def transcript_references(entry: dict[str, Any]) -> list[TranscriptReference]:
    candidates: list[TranscriptReference] = []
    raw = entry.get("podcast_transcript") or entry.get("transcript")
    values = raw if isinstance(raw, list) else [raw] if raw else []
    for value in values:
        if isinstance(value, dict):
            url = value.get("url") or value.get("href")
            if url:
                candidates.append(
                    TranscriptReference(
                        url=str(url),
                        mime_type=value.get("type"),
                        language=value.get("language"),
                        rel=value.get("rel"),
                    )
                )
    return candidates
