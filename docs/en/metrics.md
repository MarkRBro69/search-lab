# Metrics

## Overview

Search Lab measures **how well** each search configuration ranks documents for your queries. Application-level metrics are computed in the service so they work across **bm25**, **semantic**, **hybrid**, and **rrf** modes. Separately, OpenSearch’s native **`_rank_eval`** API provides BM25-only metrics with a fixed set of metric names — **NDCG is not one of them** in that API.

For all metrics below, **higher is better** unless noted.

## Application metrics (`POST /api/v1/eval` and benchmark runs)

These apply when you supply **ground-truth relevant document IDs** and compare them to the ranked results.

### NDCG@K (Normalised Discounted Cumulative Gain)

**Definition:** Rewards placing highly relevant documents **near the top** of the list. Uses a gain based on whether each hit is relevant and **discounts** positions further down so mistakes at rank 1 hurt more than at rank 10.

**Range:** Typically **0–1** (normalised).

**Interpretation:** **1** means perfect ordering relative to your labels; **0** means no useful ranking signal at the top.

### MRR (Mean Reciprocal Rank)

**Definition:** For a single query, take **1 divided by the rank of the first relevant document** (e.g. first relevant at rank 3 → 1/3). Across multiple queries in a benchmark, MRR is averaged accordingly.

**Range:** **0–1**.

**Interpretation:** **1** means the first result is always relevant; lower values mean users must scroll more before hitting a relevant document.

### Precision@K

**Definition:** Of the **top K** results returned, the **fraction that are relevant** (appear in your relevant ID set).

**Range:** **0–1**.

**Interpretation:** Measures **density of good results in the short list** — useful when K is small (e.g. first page).

### Recall@K

**Definition:** Of **all** document IDs you marked relevant for that query, the **fraction that appear somewhere in the top K** results.

**Range:** **0–1**.

**Interpretation:** Measures **coverage** — whether you surfaced most of the known-good documents within K. If you only label one document, recall is often 0 or 1.

---

## Benchmark-only metrics

Benchmark runs evaluate **every pair** (algorithm × query template) and store extra diagnostics.

### `latency_ms`

**Definition:** Wall-clock time for the search request for that pair (milliseconds).

**Interpretation:** **Lower is better** for user experience and cost; compare across algorithms on the same hardware and data volume.

### `score_separation`

**Definition:** The **mean score of relevant hits** minus the **mean score of non-relevant hits** in the returned list (for that query and algorithm).

**Interpretation:** **Larger positive values** suggest the ranker assigns **higher scores to relevant documents** than to irrelevant ones in the same result set — a useful diagnostic when headline metrics look similar.

---

## Native OpenSearch `_rank_eval` (`POST /api/v1/eval/rank-eval`)

This path calls OpenSearch’s **built-in** ranking evaluation for **BM25 queries** on a **single logical index**. It does **not** run your hybrid or RRF pipeline.

**Constraints:**

- **BM25 only** (not hybrid / semantic / RRF quality evaluation — use `POST /api/v1/eval` for those).
- **Single index key** — you must not use the logical key **`all`**; ratings target one physical index.

**Valid `metric` values** in the request body:

| Value | Role |
|-------|------|
| `dcg` | Discounted Cumulative Gain (default in API) |
| `precision` | Precision-style metric at top K |
| `recall` | Recall-style metric at top K |
| `mean_reciprocal_rank` | MRR-style metric from OpenSearch |

**NDCG is not supported** in this native API. For **NDCG@K**, use **`POST /api/v1/eval`** or a **benchmark run**, where NDCG is computed in the application layer.

## Where to see metrics in the UI

- **Search** — **Eval marks** panel (single-query application metrics) and **rank-eval** panel (native `_rank_eval`, BM25, one index).
- **Experiments → Benchmark** — full matrix results: NDCG@K, MRR, Precision@K, Recall@K, **latency_ms**, **score_separation**, plus summaries per algorithm.

---

[← User guide index](README.md) · [Русская версия](../ru/metrics.md)
