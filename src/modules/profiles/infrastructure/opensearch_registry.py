"""OpenSearch client cache and factory (basic auth and AWS SigV4)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import boto3
import structlog
from opensearchpy import OpenSearch
from requests_aws4auth import AWS4Auth

from src.modules.profiles.domain.models import OpenSearchAuthType, OpenSearchConfig

logger = structlog.get_logger()

_client_cache: dict[str, OpenSearch] = {}


def _aws_sigv4_auth(config: OpenSearchConfig) -> AWS4Auth:
    region = config.aws_region or "us-east-1"
    service = "es"
    session = boto3.Session(region_name=region)
    creds = session.get_credentials()
    if creds is None:
        msg = "AWS SigV4 auth requires credentials from the default credential chain (env vars or IAM role)"
        raise ValueError(msg)
    frozen = creds.get_frozen_credentials()
    return AWS4Auth(
        frozen.access_key,
        frozen.secret_key,
        region,
        service,
        session_token=frozen.token,
    )


def _build_opensearch_client(config: OpenSearchConfig) -> OpenSearch:
    host_cfg = {"host": config.host, "port": config.port}
    kwargs: dict[str, object] = {
        "hosts": [host_cfg],
        "use_ssl": config.use_ssl,
        "verify_certs": False,
        "http_compress": True,
    }

    if config.auth_type == OpenSearchAuthType.NONE:
        pass
    elif config.auth_type == OpenSearchAuthType.BASIC:
        kwargs["http_auth"] = (config.username, config.password)
    elif config.auth_type == OpenSearchAuthType.AWS_SIGNATURE_V4:
        kwargs["http_auth"] = _aws_sigv4_auth(config)
    else:
        msg = f"Unsupported auth type: {config.auth_type}"
        raise ValueError(msg)

    client = OpenSearch(**kwargs)
    log = logger.bind(module="profiles", operation="_build_opensearch_client")
    log.info("opensearch_client_built", host=config.host, port=config.port, auth=config.auth_type)
    return client


@dataclass(frozen=True, slots=True)
class EphemeralPingOutcome:
    """Result of a one-off OpenSearch ping (not cached client)."""

    ok: bool
    latency_ms: float | None
    error: str | None


def build_ephemeral_opensearch_client(config: OpenSearchConfig) -> OpenSearch:
    """Same transport/auth as cached path via _build_opensearch_client; not stored in _client_cache."""
    return _build_opensearch_client(config)


async def ping_opensearch_ephemeral(config: OpenSearchConfig) -> EphemeralPingOutcome:
    """Build ephemeral client, run ping in asyncio.to_thread, always close client in finally."""
    log = logger.bind(module="profiles", operation="ping_opensearch_ephemeral")
    client = build_ephemeral_opensearch_client(config)
    try:
        t0 = time.perf_counter()
        try:
            ping_ok = await asyncio.to_thread(client.ping)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if not ping_ok:
                log.warning("opensearch_ping_returned_false")
                return EphemeralPingOutcome(
                    ok=False, latency_ms=latency_ms, error="OpenSearch ping failed"
                )
            return EphemeralPingOutcome(ok=True, latency_ms=latency_ms, error=None)
        except Exception:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            log.warning("opensearch_ping_failed")
            return EphemeralPingOutcome(
                ok=False, latency_ms=latency_ms, error="OpenSearch ping failed"
            )
    finally:
        client.close()


def get_or_create_opensearch_client(profile_id: str, config: OpenSearchConfig) -> OpenSearch:
    """Return cached OpenSearch client for profile_id or create and cache it."""
    if profile_id in _client_cache:
        return _client_cache[profile_id]
    client = _build_opensearch_client(config)
    _client_cache[profile_id] = client
    return client


def evict_opensearch_client(profile_id: str) -> None:
    """Close and remove a cached client (e.g. after profile connection settings change)."""
    cached = _client_cache.pop(profile_id, None)
    if cached is not None:
        cached.close()


def close_all_opensearch_clients() -> None:
    """Close all cached clients and clear the registry."""
    for client in _client_cache.values():
        client.close()
    _client_cache.clear()
