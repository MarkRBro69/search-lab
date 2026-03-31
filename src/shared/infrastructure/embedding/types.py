"""Embedding configuration types (shared between profiles and embedding backends)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class EmbeddingProvider(StrEnum):
    LOCAL_SENTENCE_TRANSFORMERS = "local_sentence_transformers"
    AWS_BEDROCK = "aws_bedrock"


class EmbeddingConfig(BaseModel):
    """Embedding provider configuration."""

    model_config = ConfigDict(populate_by_name=True)

    provider: EmbeddingProvider
    model_name: str
    aws_region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None

    @model_validator(mode="after")
    def validate_bedrock_fields(self) -> EmbeddingConfig:
        if self.provider == EmbeddingProvider.AWS_BEDROCK and not self.aws_region:
            msg = "AWS_BEDROCK provider requires aws_region"
            raise ValueError(msg)
        return self
