# Getting started

## Prerequisites

You need:

- **Python 3.14+** and **[uv](https://docs.astral.sh/uv/)** for dependencies and running the app
- **Docker** (with Compose) for OpenSearch and MongoDB locally

For a full checklist (pre-commit, `.env`, optional tools), see [Developer setup](../developer-setup.md). This page stays short on purpose.

## Run the stack

From the project root:

```powershell
# Install Python dependencies
uv sync --all-extras

# Start OpenSearch and MongoDB
docker-compose up -d opensearch mongodb

# Optional: load sample documents (if you use the project seed script)
uv run python scripts/seed.py

# Start the application
uv run uvicorn src.main:app --reload
```

If you prefer a Makefile target and the repo defines it, `make dev` is equivalent to running uvicorn with reload.

Default URLs (unless you change the host/port):

- **Web UI:** `http://localhost:8000`
- **Swagger:** `http://localhost:8000/docs`

## Open the UI

The main layout uses **three tabs** in the header:

| Tab | Purpose |
|-----|---------|
| **Search** | Run searches, optional explain, eval marks, rank-eval |
| **Experiments** | Algorithms, query templates, benchmark runs |
| **Settings** | Connection profiles: create, edit, activate, test |

The **header** also shows which **connection profile** is active (after you activate one in Settings). All search and document operations use the **active profile**’s OpenSearch endpoint, embedding backend, and logical index mapping.

### Search tab — sidebar and panels

In **Search**, the sidebar typically includes:

- **Mode** — `bm25`, `semantic`, `hybrid`, or `rrf`
- **Collection** — logical index key (including `all` where supported)
- **Size** — number of hits to return
- **Explain** — score breakdown (hybrid/RRF) or BM25 explanation tree where applicable
- **Filters** — optional structured filters (see below)

Additional areas:

- **Eval marks** — mark relevant document IDs and drive **POST /api/v1/eval**-style evaluation from the UI
- **Rank-eval** — batch BM25 evaluation via **POST /api/v1/eval/rank-eval** (single index only; not `all`)

### Experiments tab

Sub-tabs:

- **Algorithms** — saved search configurations
- **Templates** — saved queries + relevant IDs
- **Benchmark** — choose algorithms × templates, run matrix, inspect results

Benchmark execution uses the **same active profile** as Search and Settings.

### Settings tab

Manage **connection profiles**: create, edit, **activate**, and **test** connectivity (OpenSearch + embedding). The active profile name appears in the header.

## First-time flow

1. Open **Settings** and **create** a connection profile (or select an existing one) with correct OpenSearch and embedding settings.
2. **Activate** the profile you want to use.
3. Optionally **Test** the profile to confirm OpenSearch and embeddings respond.
4. Go to **Search**, pick **mode**, **collection**, and **size**, enter a **query**, and run the search.

After you see results, you can mark relevant IDs and use evaluation features, or move to **Experiments** for library-based benchmarks.

## Search modes overview

| Mode | What it does | Notes |
|------|----------------|-------|
| **bm25** | Keyword search with TF-IDF-style scoring (normalised for display) | Strong for exact terms and identifiers |
| **semantic** | KNN vector search over document embeddings | Strong for paraphrases and descriptive queries |
| **hybrid** | Weighted combination of BM25 and KNN scores | `bm25_weight` and `knn_weight` must **sum to 1.0** |
| **rrf** | Reciprocal Rank Fusion of BM25 and KNN ranked lists | Rank-based blend; no manual weight tuning like hybrid |

### Filters

Optional filters follow the same shape as the API:

- **`filter_term`** — term-style filters (exact-match style constraints you configure per field)
- **`filter_gte`** — lower bounds (format `"field:value"` as supported by your index)
- **`filter_lte`** — upper bounds (same string format)

Unknown fields may be ignored when searching across multiple physical indices so the UI stays domain-agnostic.

## User-significant HTTP endpoints

All API routes below are under **`/api/v1`** except health and docs:

| Method | Path | Role |
|--------|------|------|
| GET | `/api/v1/search` | Search documents |
| GET | `/api/v1/search/explain/{index_key}/{doc_id}` | BM25 explanation for one document (`q` query param) |
| POST | `/api/v1/eval` | One query + relevant IDs → NDCG@K, MRR, Precision@K, Recall@K |
| POST | `/api/v1/eval/rank-eval` | Batch BM25 `_rank_eval` (single index; not `all`) |
| POST | `/api/v1/documents/{index_key}` | Create document |
| GET | `/api/v1/documents/{index_key}/{doc_id}` | Get document |
| PUT | `/api/v1/documents/{index_key}/{doc_id}` | Update document |
| DELETE | `/api/v1/documents/{index_key}/{doc_id}` | Delete document |
| GET/POST/PUT/DELETE | `/api/v1/profiles` … | Profiles CRUD (see [profiles.md](profiles.md)) |
| POST | `/api/v1/profiles/{id}/activate` | Activate profile |
| POST | `/api/v1/profiles/{id}/test` | Test connections |
| GET/POST/DELETE | `/api/v1/experiments/algorithms` … | Algorithms (see [experiments.md](experiments.md)) |
| GET/POST/PUT/DELETE | `/api/v1/experiments/templates` … | Templates |
| POST/GET/DELETE | `/api/v1/experiments/benchmark` … | Benchmark runs |

**Outside `/api/v1`:**

| Method | Path | Role |
|--------|------|------|
| GET | `/health` | Liveness |
| GET | `/docs` | Swagger UI |

## Next steps

- [Metrics](metrics.md) — interpret NDCG@K, MRR, latency, and native rank_eval metrics
- [Connection profiles](profiles.md) — indices, auth, secrets, full profile API table
- [Experiments](experiments.md) — algorithms without per-algorithm index field; templates hold `index`

---

[← User guide index](README.md) · [Русская версия](../ru/getting-started.md)
