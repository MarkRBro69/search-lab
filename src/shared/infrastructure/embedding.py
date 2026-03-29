"""Shared embedding service singleton (sentence-transformers)."""

from __future__ import annotations

import asyncio
from functools import partial

import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger()

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None


def _load_model() -> SentenceTransformer:
    global _model  # noqa: PLW0603
    if _model is None:
        logger.info("embedding_model_loading", model=MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("embedding_model_loaded", model=MODEL_NAME)
    return _model


def get_model() -> SentenceTransformer:
    return _load_model()


async def embed_async(text: str) -> list[float]:
    """Encode text in a thread pool to avoid blocking the event loop."""
    model = get_model()
    loop = asyncio.get_running_loop()
    fn = partial(model.encode, text, normalize_embeddings=True)
    vector = await loop.run_in_executor(None, fn)
    return vector.tolist()
