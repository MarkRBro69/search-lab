FROM python:3.14-slim

# Create non-root user early so COPY --chown works without chown -R
RUN useradd --no-create-home --no-log-init --system appuser

WORKDIR /app

# Install uv (system-level tool, stays root)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and install (root is fine, .venv goes to /app)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

# Copy source files already owned by appuser — no chown -R needed
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser static/ ./static/

# Fix ownership of .venv only (one directory, not recursive over src/static)
RUN chown -R appuser:appuser /app/.venv

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_LINK_MODE=copy
ENV HF_HOME=/app/.hf_cache

USER appuser

# Pre-download embedding model during build (~90MB, cached in image)
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
