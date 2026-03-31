# ADR-0003: Connection Profiles — dynamic engine/model/index configuration

**Date:** 2026-03-30
**Status:** Accepted

## Context
The platform needed to support multiple OpenSearch deployments (local, AWS managed) with
different authentication methods (none, basic, AWS SigV4), different embedding backends
(local sentence-transformers, AWS Bedrock), and different index names per environment.
Previously all configuration came from environment variables with a single global singleton.

## Decision
Introduce a `profiles` module with a `ConnectionProfile` aggregate stored in MongoDB.
Exactly one profile is `is_active=True` at a time. All search and experiment endpoints
resolve the active profile via `Depends(get_active_profile_bundle)` which returns a
typed bundle: `(opensearch_client, indices, embed_fn)`. OpenSearch clients are cached
by `profile_id` in an in-memory registry. Clients are created on demand and closed at
app shutdown.

`EmbeddingConfig` and `EmbeddingProvider` live in `src/shared/infrastructure/embedding/types.py`
(not in `profiles/domain`) to avoid a circular dependency: `shared/embedding/factory.py` needs
the config type without depending on the `profiles` module.

## Consequences
- All search endpoints gain a `Depends(get_active_profile_bundle)` dependency
- `search_service.search()` and repository functions accept explicit `index_alias` and `embed` params
- `execute_benchmark` snapshots `(client, index_alias, embed)` at start — no mid-flight profile switch
- Secrets (password, AWS keys) are never returned by the API; UI must re-enter credentials on edit
- Default profile is seeded from env vars at startup if the profiles collection is empty
