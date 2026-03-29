# Agent Instructions — Search Lab

This file provides essential context for all LLM agents working on this project.
Read this file first before making any changes.

## Project Purpose

A FastAPI-based **evaluation platform** for comparing OpenSearch search algorithms.
The platform allows engineers to define named algorithm configurations (BM25, semantic,
hybrid, RRF), build a library of queries with ground-truth relevance judgements, and run
N-algorithm × M-query benchmark matrices — collecting NDCG@K, MRR, Precision@K, Recall@K,
latency, and score-separation metrics. Results are stored in MongoDB for historical comparison.

LLM-agent integration (query enrichment, reranking) is planned for a future iteration.

## Tech Stack

- **Python 3.14** — runtime
- **uv** — package manager and virtual environment (never use `pip` directly)
- **ruff** — linter, formatter, import sorter (single tool, replaces black/flake8/isort)
- **FastAPI** — async web framework
- **OpenSearch 2.x** — search engine (BM25, KNN, RRF)
- **sentence-transformers** — local embedding model `all-MiniLM-L6-v2` (384d)
- **MongoDB + Motor** — async storage for benchmark results and experiment configs
- **structlog** — structured logging (JSON in prod, readable in dev)
- **pytest + pytest-asyncio** — testing (`asyncio_mode = "auto"`)
- **Docker + docker-compose** — containerization and local infrastructure

## Architecture

This project follows **Clean Architecture** inside a **Modular Monolith**.

### Layer Structure (per module)

```
Presentation  →  Application  →  [Domain]  ←  Infrastructure
(routers,         (use cases,     (entities,    (OpenSearch,
 schemas)          commands,       value         LLM clients,
                   queries)        objects)      repos)
```

- Dependency direction: always inward. Infrastructure depends on Domain/Application, never the reverse.
- `Domain` layer is **optional** — only add it when non-trivial business logic exists.

### Module Boundaries

```
src/modules/
  search/                   ← search algorithms, indexing, per-query eval metrics
    api.py                  ← public interface, only import from here in other modules
    presentation/           ← /search, /eval, /documents routes
    application/            ← search_service, eval_service, indexing_service
    infrastructure/         ← OpenSearch repository (BM25, KNN, RRF, rank_eval)
  experiments/              ← CORE: benchmark platform (N algos × M queries)
    api.py
    domain/                 ← Algorithm, QueryTemplate, BenchmarkRun aggregates
    application/            ← experiments_service (async N×M runner)
    infrastructure/         ← MongoDB repository (algorithms, templates, runs)
    presentation/           ← /experiments/algorithms, /templates, /benchmark routes
  agents/                   ← (stub) LLM agents for future query enrichment
    api.py
```

- Modules **never** import each other's internals directly.
- Cross-module calls go through `src/modules/{name}/api.py` only.
- Shared base classes and config live in `src/shared/`.

## Detailed Rules

All coding rules are in `.cursor/rules/`. Read the relevant file before editing:

| File | Scope | Purpose |
|---|---|---|
| `project-overview.mdc` | always | Stack summary, global constraints |
| `communication.mdc` | always | Language (ru), shell (PowerShell), response style |
| `architecture.mdc` | always | Module structure, dependency rules |
| `agent-workflow.mdc` | always | Pre-Stage 0 decomposition + 5-stage pipeline per task; deviation requires explicit user approval |
| `tooling.mdc` | always | uv, ruff, pytest commands |
| `git-conventions.mdc` | always | Commit format, branch naming |
| `logging.mdc` | always | structlog usage, required fields |
| `fastapi-conventions.mdc` | `**/*.py` | Routers, Pydantic, error handling |
| `testing.mdc` | `tests/**/*.py` | Test structure, fixtures, naming |
| `opensearch-patterns.mdc` | `src/modules/search/infrastructure/**` | Query DSL, index naming |
| `experiments-patterns.mdc` | `src/modules/experiments/**` | Algorithm/Template/BenchmarkRun patterns |
| `llm-agent-integration.mdc` | `src/modules/agents/**` | LLM client patterns, tool schemas |

## Developer Profiles (Local Overrides)

Each developer can override agent behavior locally (language, shell, OS preferences).
Local profiles live in `.cursor/rules/local/` and are **gitignored**.

Check `.cursor/rules/local/` for any active developer profile before interacting.
If a profile exists, respect its settings (e.g. communication language, shell syntax).

See `.cursor/rules/local/README.md` for instructions on creating a profile.

## Global Skills

The following personal skills are active for all projects and apply here:

| Skill | When it activates |
|---|---|
| `knowledge-update` | After every Stage 4 PASS — proposes updates to rules/docs/skills |
| `agent-init` | When setting up or auditing project rules |

## Key Constraints

- All I/O must be **async** — no synchronous database or HTTP calls
- **No `Any` types** — all type annotations must be explicit
- **No magic strings** — use enums or constants
- **No `pip install`** — always use `uv add`
- Secrets and PII must **never** appear in logs
- Every endpoint must have a Pydantic request and response model

## Directory Layout

```
new_search/
├── src/
│   ├── main.py              # FastAPI app, lifespan, middleware
│   ├── shared/              # Shared infra: OpenSearch client, MongoDB client, embeddings
│   └── modules/
│       ├── search/          # Search algorithms + eval metrics
│       ├── experiments/     # Benchmark platform (core of this project)
│       └── agents/          # (stub) LLM enrichment
├── scripts/
│   ├── seed.py              # Populate OpenSearch with test documents
│   └── semantic_search_demo.py
├── static/
│   └── index.html           # Web UI
├── tests/
│   ├── unit/                # Pure logic, all I/O mocked
│   ├── integration/         # Real OpenSearch + MongoDB via docker-compose
│   └── e2e/                 # Full request/response scenarios
├── docs/
│   ├── decisions/           # Architecture Decision Records (ADRs)
│   └── developer-setup.md
└── .cursor/
    ├── rules/               # Agent rules (.mdc files)
    │   └── local/           # Personal developer overrides (gitignored)
    └── templates/           # Output templates for agent stages
```
