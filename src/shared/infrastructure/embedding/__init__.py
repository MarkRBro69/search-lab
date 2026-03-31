"""Embedding backends and factory."""

from src.shared.infrastructure.embedding.factory import build_embedding_backend
from src.shared.infrastructure.embedding.local_sentence_transformers import (
    EMBEDDING_DIM,
    embed_local,
    get_local_model_name,
    get_model,
    init_local_embedding_model,
)

__all__ = [
    "EMBEDDING_DIM",
    "build_embedding_backend",
    "embed_local",
    "get_local_model_name",
    "get_model",
    "init_local_embedding_model",
]
