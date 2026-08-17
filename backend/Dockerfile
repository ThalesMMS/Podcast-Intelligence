FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.32

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/podcast-intelligence \
    && chown -R appuser:appuser /app /tmp/podcast-intelligence

USER appuser

EXPOSE 8000 8001
CMD ["uvicorn", "podcast_intelligence.main:app", "--host", "0.0.0.0", "--port", "8000"]
