# ADR-0005: SearchMode as Shared StrEnum

**Date:** 2026-03-30
**Status:** Accepted

## Context

Search mode (`"bm25"`, `"semantic"`, `"hybrid"`, `"rrf"`) appeared as duplicated
`Literal[...]` in four places across two modules:

- `SearchParams.mode: str` — application layer, search module
- `Algorithm.mode: Literal[...]` — domain model, experiments module
- `AlgorithmCreate.mode: str` — API schema, experiments presentation
- String comparisons `if params.mode == "bm25":` — search_service branching

This caused drift risk (adding a new mode required changes in 4+ places), magic string
comparisons, and no type-level guarantee that the two modules agreed on the same values.

## Decision

Introduce `SearchMode(str, StrEnum)` in `src/shared/search_mode.py` as the single
source of truth. Values: `BM25 = "bm25"`, `SEMANTIC = "semantic"`,
`HYBRID = "hybrid"`, `RRF = "rrf"`.

All modules import `SearchMode` from this shared location. It is re-exported via
`src/modules/search/api.py` for external module consumers (e.g. experiments).

## Consequences

- **One change point** when adding a new search mode
- **Type-safe comparisons** (`params.mode == SearchMode.BM25` instead of `"bm25"`)
- **StrEnum serializes to plain string** in JSON and MongoDB — no schema migration needed;
  existing stored values remain valid
- **When adding a new mode:** update `SearchMode` in `src/shared/search_mode.py`,
  add branch in `search_service.py`, and update `experiments-patterns.mdc` docs
