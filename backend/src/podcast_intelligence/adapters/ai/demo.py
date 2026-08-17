from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from podcast_intelligence.domain.types import (
    AnswerDocument,
    ChapterSummary,
    EpisodeSummaryDocument,
    KeyPoint,
    ProviderCapabilities,
    RetrievedChunk,
    SectionDigest,
    TranscriptionResult,
    TranscriptSegmentData,
)

_WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


def _sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_RE.split(cleaned) if part.strip()]
    return parts or [cleaned]


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = [word.lower() for word in _WORD_RE.findall(text)]
    counts = Counter(word for word in words if len(word) > 3 and word not in _STOPWORDS)
    return [word for word, _ in counts.most_common(limit)]


def _extractive(text: str, max_sentences: int) -> str:
    sentences = _sentences(text)
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    keywords = set(_keywords(text, limit=16))
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        terms = [term.lower() for term in _WORD_RE.findall(sentence)]
        keyword_hits = sum(1 for term in terms if term in keywords)
        position_bonus = 1.0 / (index + 1)
        length_penalty = abs(len(terms) - 22) / 50
        scored.append((keyword_hits + position_bonus - length_penalty, index, sentence))
    selected = sorted(scored, reverse=True)[:max_sentences]
    return " ".join(sentence for _, _, sentence in sorted(selected, key=lambda item: item[1]))


class DemoTranscriber:
    """Deterministic no-key adapter used to exercise the complete pipeline.

    It intentionally does not claim to recognize the supplied audio. In demo mode it creates a
    marked transcript so infrastructure, storage, indexing, summaries and chat can be tested
    without sending media to a third party. Configure the OpenAI adapter for real transcription.
    """

    provider_name = "demo"
    model_name = "synthetic-transcript-v1"

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        known_speakers: dict[str, Path] | None = None,
    ) -> TranscriptionResult:
        del language, known_speakers
        size_mb = audio_path.stat().st_size / (1024 * 1024) if audio_path.exists() else 0
        texts = [
            "This is a synthetic transcript created by demo mode.",
            "The audio file was received, stored, and prepared by the local pipeline.",
            "For real speech recognition, configure AI_PROFILE=openai and provide OPENAI_API_KEY, or implement another transcription adapter.",
            f"The processed asset is approximately {size_mb:.2f} megabytes.",
            "Later stages remain operational: segmentation, deterministic embeddings, structured summaries, search, and chat with citations.",
        ]
        segments: list[TranscriptSegmentData] = []
        cursor_ms = 0
        for ordinal, text in enumerate(texts):
            duration_ms = max(3500, len(text.split()) * 330)
            segments.append(
                TranscriptSegmentData(
                    ordinal=ordinal,
                    start_ms=cursor_ms,
                    end_ms=cursor_ms + duration_ms,
                    text=text,
                    speaker_label="SPEAKER_00" if ordinal % 2 == 0 else "SPEAKER_01",
                    confidence=1.0,
                    language="en",
                    metadata={"synthetic": True},
                )
            )
            cursor_ms += duration_ms
        return TranscriptionResult(
            text=" ".join(texts),
            segments=segments,
            language="en",
            provider=self.provider_name,
            model=self.model_name,
            metadata={"synthetic": True, "warning": "Not derived from the audio content"},
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider_name,
            kind="transcription",
            model=self.model_name,
            capabilities={
                "real_transcription": False,
                "diarization": True,
                "word_timestamps": False,
                "offline": True,
            },
        )


class DeterministicEmbeddingProvider:
    """Signed feature-hashing embeddings for local tests and deterministic development."""

    provider_name = "demo"
    model_name = "feature-hash-v1"

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        words = [word.lower() for word in _WORD_RE.findall(text)]
        features = words + [f"{a}_{b}" for a, b in pairwise(words)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider_name,
            kind="embedding",
            model=self.model_name,
            capabilities={"dimension": self.dimension, "offline": True, "semantic": False},
        )


class DemoLanguageModel:
    provider_name = "demo"
    model_name = "extractive-v1"

    def summarize_section(
        self, episode_title: str, section_title: str, transcript: str, segment_ids: list[str]
    ) -> SectionDigest:
        del episode_title
        summary = _extractive(transcript, max_sentences=3)
        return SectionDigest(
            title=section_title,
            summary=summary,
            start_ms=0,
            end_ms=0,
            supporting_segment_ids=segment_ids[:12],
            topics=_keywords(transcript),
        )

    def synthesize_summary(
        self, episode_title: str, section_digests: Sequence[SectionDigest]
    ) -> EpisodeSummaryDocument:
        combined = " ".join(digest.summary for digest in section_digests)
        executive = _extractive(combined, max_sentences=4)
        detailed = "\n\n".join(
            f"{digest.title}: {digest.summary}" for digest in section_digests if digest.summary
        )
        chapters = [
            ChapterSummary(
                title=digest.title,
                summary=digest.summary,
                start_ms=digest.start_ms,
                end_ms=digest.end_ms,
                supporting_segment_ids=digest.supporting_segment_ids,
            )
            for digest in section_digests
        ]
        takeaways = [
            KeyPoint(text=digest.summary, supporting_segment_ids=digest.supporting_segment_ids[:5])
            for digest in section_digests[:8]
            if digest.summary
        ]
        return EpisodeSummaryDocument(
            executive_summary=executive or f"Summary unavailable for {episode_title}.",
            detailed_summary=detailed or executive,
            chapters=chapters,
            key_takeaways=takeaways,
            topics=_keywords(combined, limit=12),
        )

    def answer(
        self,
        question: str,
        contexts: Sequence[RetrievedChunk],
        conversation_history: Sequence[dict[str, str]],
    ) -> AnswerDocument:
        del conversation_history
        if not contexts:
            return AnswerDocument(
                answer="There is not enough evidence in the indexed transcript to answer.",
                cited_segment_ids=[],
                insufficient_evidence=True,
            )
        keywords = set(_keywords(question, limit=12))
        ranked = sorted(
            contexts,
            key=lambda context: (
                sum(term in context.text.lower() for term in keywords),
                context.combined_score,
            ),
            reverse=True,
        )
        selected = ranked[:3]
        evidence = " ".join(_extractive(item.text, max_sentences=2) for item in selected)
        cited_ids: list[str] = []
        for item in selected:
            cited_ids.extend(item.segment_ids)
        return AnswerDocument(
            answer=_extractive(evidence, max_sentences=5),
            cited_segment_ids=list(dict.fromkeys(cited_ids))[:12],
            insufficient_evidence=False,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider_name,
            kind="llm",
            model=self.model_name,
            capabilities={
                "structured_outputs": True,
                "grounded_answers": True,
                "offline": True,
                "generative": False,
            },
        )
