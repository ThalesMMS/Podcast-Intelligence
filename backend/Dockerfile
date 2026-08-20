FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

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
