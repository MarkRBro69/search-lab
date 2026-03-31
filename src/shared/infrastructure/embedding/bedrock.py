"""AWS Bedrock embedding backend (async via thread pool)."""

from __future__ import annotations

import asyncio
import json

import boto3

from src.shared.infrastructure.embedding.types import EmbeddingConfig


async def embed_bedrock(text: str, config: EmbeddingConfig) -> list[float]:
    """Invoke Bedrock embedding model; runs boto3 in a worker thread."""

    def _call() -> list[float]:
        kwargs: dict[str, str] = {"region_name": config.aws_region or "us-east-1"}
        if config.aws_access_key_id and config.aws_secret_access_key:
            kwargs["aws_access_key_id"] = config.aws_access_key_id
            kwargs["aws_secret_access_key"] = config.aws_secret_access_key
        client = boto3.client("bedrock-runtime", **kwargs)
        body = json.dumps({"inputText": text})
        response = client.invoke_model(modelId=config.model_name, body=body)
        payload = response["body"].read()
        result = json.loads(payload)
        embedding = result["embedding"]
        return [float(x) for x in embedding]

    return await asyncio.to_thread(_call)
