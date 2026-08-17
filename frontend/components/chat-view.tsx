"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { MessageIcon, SendIcon } from "@/components/icons";
import { api } from "@/lib/api";
import { createClientId } from "@/lib/client-id";
import { localizeError } from "@/lib/errors";
import { formatDuration } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/provider";
import type { Citation } from "@/lib/types";

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  insufficient?: boolean;
}

const suggestions: MessageKey[] = [
  "chat.suggestionArguments",
  "chat.suggestionDisagreement",
  "chat.suggestionRecommendations",
];

export function ChatView({
  episodeId,
  ready,
  onSeek,
}: {
  episodeId: string;
  ready: boolean;
  onSeek: (milliseconds: number) => void;
}) {
  const { t } = useI18n();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, sending]);

  async function submitQuestion(value: string) {
    const normalized = value.trim();
    if (!normalized || sending || !ready) return;
    setQuestion("");
    setError(null);
    setMessages((current) => [
      ...current,
      { id: createClientId(), role: "user", content: normalized, citations: [] },
    ]);
    setSending(true);
    try {
      let activeConversation = conversationId;
      if (!activeConversation) {
        const created = await api.createConversation(episodeId);
        activeConversation = created.id;
        setConversationId(activeConversation);
      }
      const response = await api.ask(activeConversation, normalized);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          citations: response.citations,
          insufficient: response.insufficient_evidence,
        },
      ]);
    } catch (cause) {
      setError(cause);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion(question);
  }

  return (
    <div className="chatView">
      <div className="chatHeader">
        <div>
          <span className="panelLabel">{t("chat.eyebrow")}</span>
          <h2>{t("chat.title")}</h2>
        </div>
        <span className="groundingState">{t("chat.grounding")}</span>
      </div>
      <div className="chatMessages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chatWelcome">
            <span className="emptySymbol">
              <MessageIcon size={25} />
            </span>
            <h3>{t("chat.welcome")}</h3>
            <p>{t("chat.explanation")}</p>
            <div className="suggestionList">
              {suggestions.map((suggestion) => (
                <button
                  disabled={!ready}
                  key={suggestion}
                  onClick={() => void submitQuestion(t(suggestion))}
                  type="button"
                >
                  {t(suggestion)}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {messages.map((message) => (
          <article className={`chatMessage ${message.role}`} key={message.id}>
            <span className="messageRole">
              {message.role === "user" ? t("chat.user") : t("chat.assistant")}
            </span>
            <p>{message.content}</p>
            {message.insufficient ? (
              <small className="insufficientNote">{t("chat.insufficient")}</small>
            ) : null}
            {message.citations.length ? (
              <div className="citationList">
                {message.citations.map((citation) => (
                  <button
                    key={citation.segment_id}
                    onClick={() => onSeek(citation.start_ms)}
                    type="button"
                  >
                    <strong>{formatDuration(citation.start_ms)}</strong>
                    <span>{citation.speaker ?? t("transcript.speaker")}</span>
                    <q>{citation.quote}</q>
                  </button>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {sending ? (
          <div className="thinkingState">
            <span />
            <span />
            <span /> {t("chat.consulting")}
          </div>
        ) : null}
        {error ? (
          <div className="notice errorNotice compactNotice">
            {localizeError(error, t, "errors.chatAnswer")}
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>
      <form className="chatComposer" onSubmit={handleSubmit}>
        <textarea
          aria-label={t("chat.questionLabel")}
          disabled={!ready || sending}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submitQuestion(question);
            }
          }}
          placeholder={ready ? t("chat.readyPlaceholder") : t("chat.waitingPlaceholder")}
          rows={2}
          value={question}
        />
        <button
          aria-label={t("chat.send")}
          disabled={!ready || sending || !question.trim()}
          type="submit"
        >
          <SendIcon size={19} />
        </button>
      </form>
    </div>
  );
}
