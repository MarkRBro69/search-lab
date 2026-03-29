# ADR-0002: Search Evaluation Framework

## Status

Accepted

## Context

The original project description positioned this codebase as a "search service for aesthetic
medicine". In practice, the core engineering challenge is not serving search results in
production — it is **understanding which search algorithm produces the best results** for
different query types on this specific domain corpus.

The team needs to:
- Compare BM25, semantic (KNN), hybrid, and RRF on the same queries
- Measure quality objectively with standard IR metrics (NDCG, MRR, Precision, Recall)
- Accumulate ground-truth relevance judgements over time and re-use them
- Run reproducible experiments: same query set, same documents, different algorithm configs
- Identify failure modes via score distribution and score-separation analysis

A bare search API does not address these needs. Manually running curl queries and
comparing JSON responses does not scale beyond 2–3 experiments.

## Decision

Reframe the project as a **search algorithm evaluation platform** (Search Lab).

The `experiments` module becomes the **core** of the system, not a utility:

- **`Algorithm`** — a named, versioned search configuration (mode, weights, filters)
- **`QueryTemplate`** — a reusable query with ground-truth relevant document IDs
- **`BenchmarkRun`** — an N-algorithm × M-template evaluation matrix, fully persisted

The `search` module is a backend component that `experiments` orchestrates.
The FastAPI layer and the web UI serve primarily as the interface to the evaluation
workflow, not as a production search endpoint.

## Alternatives Considered

### 1. Ad-hoc scripts per experiment

Run Python/Jupyter notebooks comparing algorithms case-by-case.

**Rejected** — results are ephemeral, not reproducible, and cannot be compared across
runs with different document snapshots or team members.

### 2. External evaluation frameworks (e.g. BEIR, MTEB)

Use off-the-shelf IR evaluation toolkits.

**Rejected** — these toolkits are not designed for domain-specific document corpora with
custom field schemas (procedures, doctors, reviews) or for real-time comparison via a web UI.

### 3. OpenSearch native `_rank_eval` API only

Use the built-in ranking evaluation API.

**Partially adopted** — `_rank_eval` is used for BM25-only evaluation (`eval_router.py`).
However, it does not support semantic or hybrid modes, cannot compute score separation,
and does not persist results. The custom `BenchmarkRun` engine is needed alongside it.

## Consequences

**Easier:**
- Adding a new search mode requires only updating `Algorithm.mode` enum and the
  search repository — the benchmark engine picks it up automatically.
- Ground-truth datasets accumulate in MongoDB and can be re-used across experiments.
- Score-separation metric makes it easy to diagnose ranking problems without manual
  inspection of result lists.

**Harder:**
- The system now has two storage backends (OpenSearch + MongoDB) that must both be
  running in development. The `docker-compose.yml` provides both.
- Writing ground-truth `relevant_ids` for QueryTemplates requires manual effort or
  a labelling workflow. This is an inherent cost of offline evaluation, not a system design
  problem.

**Future work:**
- LLM-agent integration (`agents` module) for automatic relevance judgement generation
- Query expansion and reranking as additional algorithm options in `Algorithm.mode`
- Time-series tracking of metric changes as the document corpus evolves
