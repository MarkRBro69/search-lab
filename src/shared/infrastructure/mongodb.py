"""Shared Motor (async MongoDB) client singleton."""

from __future__ import annotations

import os

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = structlog.get_logger()

MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB: str = os.getenv("MONGODB_DB", "search_lab_dev")

_client: AsyncIOMotorClient | None = None  # type: ignore[type-arg]


def get_db() -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
    """Return (lazily created) Motor database instance."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URL)
        logger.info("mongodb_client_created", url=MONGODB_URL, db=MONGODB_DB)
    return _client[MONGODB_DB]


async def close_client() -> None:
    """Close Motor client — call during app shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("mongodb_client_closed")
