FROM python:3.14-slim

RUN useradd --no-create-home --no-log-init --system appuser

WORKDIR /app

# Install uv (system-level tool, stays root)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and give /app to appuser BEFORE uv sync
# At this point /app only has 2 files — chown is instant
COPY pyproject.toml uv.lock* ./
RUN mkdir -p /app/.hf_cache && chown -R appuser:appuser /app

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_LINK_MODE=copy
ENV HF_HOME=/app/.hf_cache

# Switch to appuser before uv sync — .venv is created with correct ownership instantly
USER appuser

RUN uv sync --no-dev

# Copy source files already owned by appuser
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser static/ ./static/

# Pre-download embedding model during build (~90MB, cached in image)
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
