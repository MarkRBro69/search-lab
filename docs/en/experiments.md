# Experiments

## Overview

The **Experiments** area is a small **library** of reusable pieces:

1. **Algorithms** — named search configurations (mode, weights, filters, candidate pool size).
2. **Query templates** — named queries plus **ground-truth** `relevant_ids` and which **index** to run against.
3. **Benchmark runs** — you pick **many algorithms** and **many templates**; the platform runs an **async N × M matrix** and stores **NDCG@K**, **MRR**, **Precision@K**, **Recall@K**, **latency_ms**, **score_separation**, and related stats in **MongoDB**.

Everything executes against the **currently active connection profile** (from **Settings**).

## Algorithms

An **algorithm** record captures **how** to search, not **where**:

| Field | Meaning |
|-------|---------|
| `name` / `description` | Labels for you and your team |
| `mode` | `bm25`, `semantic`, `hybrid`, or `rrf` |
| `bm25_weight` / `knn_weight` | For **hybrid**, must **sum to 1.0** |
| `num_candidates` | KNN candidate pool size (bounds enforced by API) |
| `filters` | Optional `filter_term`, `filter_gte`, `filter_lte` (same idea as Search) |

**Important:** There is **no `index` field on Algorithm**. The **index / collection** for a benchmarked query comes from the **query template** (`index` on the template, default **`all`**). That way the same algorithm definition can run on different templates that target different logical keys or `all`.

## Query templates

| Field | Meaning |
|-------|---------|
| `name` | Short label |
| `query` | The query text executed against OpenSearch |
| `index` | Logical index key (default **`all`**); defines **which collection(s)** this template uses |
| `relevant_ids` | Document IDs you consider relevant (can be filled later via update) |
| `notes` | Free-form context |

In the UI, **index** is often a **multi-select**-style control mapped to the template’s single stored key (depending on UI version).

## Benchmark run

You choose:

- **`algorithm_ids`** — which saved algorithms participate
- **`template_ids`** — which saved templates participate
- **`k`** — cutoff for **@K** metrics (NDCG@K, Precision@K, Recall@K)
- **`size`** — how many results to fetch per search (**should be ≥ k**)

**Output shape:**

- **`results[algorithm_id][template_id]`** — per-pair metrics and diagnostics
- **`summary`** — aggregated view **per algorithm** (averages across templates)

Metrics include **NDCG@K**, **MRR**, **Precision@K**, **Recall@K**, **latency_ms**, and **score_separation**, as described in [Metrics](metrics.md).

## API

All paths are under **`/api/v1/experiments`**.

### Algorithms

| Method | Path |
|--------|------|
| POST | `/api/v1/experiments/algorithms` |
| GET | `/api/v1/experiments/algorithms` |
| DELETE | `/api/v1/experiments/algorithms/{algo_id}` |

### Templates

| Method | Path |
|--------|------|
| POST | `/api/v1/experiments/templates` |
| GET | `/api/v1/experiments/templates` |
| PUT | `/api/v1/experiments/templates/{template_id}` |
| DELETE | `/api/v1/experiments/templates/{template_id}` |

### Benchmark

| Method | Path |
|--------|------|
| POST | `/api/v1/experiments/benchmark` |
| GET | `/api/v1/experiments/benchmark` |
| GET | `/api/v1/experiments/benchmark/{run_id}` |
| DELETE | `/api/v1/experiments/benchmark/{run_id}` |

## UI

Under **Experiments**:

- **Algorithms** — maintain the algorithm library
- **Templates** — maintain queries and relevance labels
- **Benchmark** — configure N × M runs and inspect results

The active **connection profile** (from **Settings**) determines OpenSearch routing, embeddings, and which logical index keys exist.

---

[← User guide index](README.md) · [Русская версия](../ru/experiments.md)
