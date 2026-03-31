"""Build async embedding callables from EmbeddingConfig."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.shared.exceptions import (
    EMBEDDING_MODEL_MISMATCH,
    UNKNOWN_EMBEDDING_PROVIDER,
    InvalidInputError,
)
from src.shared.infrastructure.embedding.bedrock import embed_bedrock
from src.shared.infrastructure.embedding.local_sentence_transformers import (
    embed_local,
    get_local_model_name,
)
from src.shared.infrastructure.embedding.types import EmbeddingConfig, EmbeddingProvider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def build_embedding_backend(
    config: EmbeddingConfig,
) -> Callable[[str], Awaitable[list[float]]]:
    """Return an async function that embeds a single text string."""
    if config.provider == EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS:
        loaded = get_local_model_name()
        if config.model_name != loaded:
            msg = (
                f"Profile requests local model {config.model_name!r} "
                f"but server loaded {loaded!r}. Restart server to change local model."
            )
            raise InvalidInputError(code=EMBEDDING_MODEL_MISMATCH, detail=msg)

        async def _local(text: str) -> list[float]:
            return await embed_local(text)

        return _local
    if config.provider == EmbeddingProvider.AWS_BEDROCK:

        async def _bedrock(text: str) -> list[float]:
            return await embed_bedrock(text, config)

        return _bedrock
    msg = f"Unknown embedding provider: {config.provider}"
    raise InvalidInputError(code=UNKNOWN_EMBEDDING_PROVIDER, detail=msg)
