"""AWS Bedrock embedding backend (async via thread pool)."""

from __future__ import annotations

import asyncio
import json

import boto3

from src.shared.infrastructure.embedding.types import EmbeddingConfig


async def embed_bedrock(text: str, config: EmbeddingConfig) -> list[float]:
    """Invoke Bedrock embedding model; runs boto3 in a worker thread."""

    def _call() -> list[float]:
        client = boto3.client("bedrock-runtime", region_name=config.aws_region or "us-east-1")
        body = json.dumps({"inputText": text})
        response = client.invoke_model(modelId=config.model_name, body=body)
        payload = response["body"].read()
        result = json.loads(payload)
        embedding = result["embedding"]
        return [float(x) for x in embedding]

    return await asyncio.to_thread(_call)
