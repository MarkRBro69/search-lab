"""Shared OpenSearch client singleton (sync, wrapped with asyncio.to_thread for async use)."""

from __future__ import annotations

import os

import structlog
from opensearchpy import OpenSearch

logger = structlog.get_logger()

_client: OpenSearch | None = None


def get_client() -> OpenSearch:
    global _client  # noqa: PLW0603
    if _client is None:
        _client = OpenSearch(
            hosts=[
                {
                    "host": os.getenv("OPENSEARCH_HOST", "localhost"),
                    "port": int(os.getenv("OPENSEARCH_PORT", "9200")),
                }
            ],
            use_ssl=os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true",
            verify_certs=False,
            http_compress=True,
        )
        log = logger.bind(module="shared.opensearch", operation="get_client")
        log.info("opensearch_client_ready")
    return _client


def close_client_sync() -> None:
    global _client  # noqa: PLW0603
    if _client is not None:
        _client.close()
        _client = None
        log = logger.bind(
            module="shared.opensearch",
            operation="close_client_sync",
            request_id="-",
        )
        log.info("opensearch_client_closed")
