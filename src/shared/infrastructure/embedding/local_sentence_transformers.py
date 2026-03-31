"""Local sentence-transformers embedding backend."""

from __future__ import annotations

import asyncio
from functools import partial

import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(module="embedding")

EMBEDDING_DIM = 384

_loaded_model: SentenceTransformer | None = None
_loaded_model_name: str | None = None


def init_local_embedding_model(model_name: str) -> None:
    """Load the SentenceTransformer model once at application startup."""
    global _loaded_model, _loaded_model_name  # noqa: PLW0603
    log = logger.bind(operation="init_local_embedding_model")
    log.info("embedding_model_loading", model=model_name)
    _loaded_model = SentenceTransformer(model_name)
    _loaded_model_name = model_name
    log.info("embedding_model_loaded", model=model_name)


def get_local_model_name() -> str:
    """Return the model name passed to init_local_embedding_model."""
    if _loaded_model_name is None:
        msg = "Local embedding model not initialised"
        raise RuntimeError(msg)
    return _loaded_model_name


def get_model() -> SentenceTransformer:
    """Return the loaded SentenceTransformer instance."""
    if _loaded_model is None:
        msg = "Local embedding model not initialised"
        raise RuntimeError(msg)
    return _loaded_model


async def embed_local(text: str) -> list[float]:
    """Encode text in a thread pool to avoid blocking the event loop."""
    model = get_model()
    loop = asyncio.get_running_loop()
    fn = partial(model.encode, text, normalize_embeddings=True)
    vector = await loop.run_in_executor(None, fn)
    return vector.tolist()
