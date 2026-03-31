"""Integration test fixtures — live OpenSearch / MongoDB (docker-compose defaults)."""

from __future__ import annotations

import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from opensearchpy import OpenSearch

pytestmark = pytest.mark.integration


@pytest.fixture
def opensearch_host() -> str:
    return os.getenv("OPENSEARCH_HOST", "localhost")


@pytest.fixture
def opensearch_port() -> int:
    return int(os.getenv("OPENSEARCH_PORT", "9200"))


@pytest.fixture
def opensearch_client(opensearch_host: str, opensearch_port: int) -> OpenSearch:
    client = OpenSearch(
        hosts=[{"host": opensearch_host, "port": opensearch_port}],
        use_ssl=os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true",
        verify_certs=False,
        http_compress=True,
    )
    try:
        client.cluster.health(request_timeout=10)
    except Exception as exc:  # noqa: BLE001 — skip with reason for any connection failure
        pytest.skip(f"OpenSearch not reachable: {exc}")
    return client


@pytest.fixture
async def motor_db():
    """Async MongoDB handle; skipped when server is down."""
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "realself_dev")
    client: AsyncIOMotorClient = AsyncIOMotorClient(url)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        client.close()
        pytest.skip(f"MongoDB not reachable: {exc}")
    try:
        yield client[db_name]
    finally:
        client.close()
