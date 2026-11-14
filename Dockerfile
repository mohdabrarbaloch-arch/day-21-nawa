FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for psycopg and bcrypt, removed in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so code changes do not invalidate the pip layer.
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY app ./app
COPY docs ./docs

# Run as a non-root user. The app writes nothing to disk (audio lives in the
# database), so this costs nothing and removes a whole class of problems.
RUN useradd --create-home --uid 10001 nawa \
    && chown -R nawa:nawa /app
USER nawa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
