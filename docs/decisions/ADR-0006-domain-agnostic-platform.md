# ADR-0006: Domain-Agnostic Search Evaluation Platform

**Status**: Accepted  
**Date**: 2026-03-30

## Context

Search Lab is a **generic search evaluation playground** — it connects to arbitrary OpenSearch
clusters, embedding models, and search databases and runs benchmarks across them. The tool
should work equally well for medical procedures, e-commerce products, legal documents,
news articles, or any other domain.

During an audit, 13 domain-specific violations were found throughout the codebase, inherited
from an early prototype that used `procedures / doctors / reviews` as fixed data shapes.

## Decision

**The platform must be fully domain-agnostic at every layer.**

Concrete rules (added to `AGENTS.md` Key Constraints):
- No hardcoded field names beyond universally-recognized `name`/`title` in the UI
- No domain-specific filter parameters in API or search params
- No typed document schemas for specific entity types (use generic `dict[str, object]`)
- No domain-specific field name detection in rendering logic (detect by type/length, not key)
- OpenAPI examples must use placeholder domain, not the medical/cosmetic prototype domain

## Violations Catalog

### CRITICAL — Breaks the tool for other domains

| # | File | Violation | Fix |
|---|---|---|---|
| 1 | `search_params.py` | 9 hardcoded filter fields (`min_rating`, `max_cost_usd`, `category`, `body_area`, `is_surgical`, `specialty`, `min_experience`, `worth_it`, `verified`) | Replace with generic `filter_terms: dict[str, str]` + `filter_ranges: list[RangeFilter]` |
| 2 | `repository.py` `build_filters()` | Maps 9 domain-specific params to hardcoded OpenSearch field names | Replace with generic filter-to-clause builder |
| 3 | `router.py` search endpoint | 9 domain-specific `Query(...)` params with domain-specific descriptions and examples | Replace with generic key-value filter params |
| 4 | `index.html` filter sidebar | 9 hardcoded filter inputs (`Min rating`, `Max cost (USD)`, `Category`, `Body area`, `Surgical only`, `Specialty (index_b)`, `Min experience (yrs)`, `Worth it (index_c)`, `Verified only`) | Replace with dynamic key-value filter UI |
| 5 | `app.js` `getFilters()` | Builds filter object with 9 domain-specific keys | Replace with generic filter builder |

> **Fixed in this session** — all 5 violations resolved as a single refactoring unit.

### MEDIUM — Domain-specific artifacts

| # | File | Violation | Fix |
|---|---|---|---|
| 6 | `document_schemas.py` | `ProcedureCreate/DoctorCreate/ReviewCreate` typed entity schemas — dead code (never imported outside this file) | **Fixed in this session** — deleted |
| 7 | `indexing_service.py` line 36 | `key = "date" if k == "review_date" else k` — hardcoded field rename for the Review entity | **Fixed in this session** — removed |
| 8 | `document_router.py` | OpenAPI path examples use `"index_a"`, `"index_b"`, `"index_c"` | **Fixed in this session** |
| 9 | `schemas.py` `RankEvalRequest` | Default `index = "index_a"`, example query `"rhinoplasty"` | **Fixed in this session** |

### LOW — Cosmetic / Documentation

| # | File | Violation | Fix |
|---|---|---|---|
| 10 | `index.html` line 13 | Static tagline `index_a · index_b · index_c` — never updates from profile | **Fixed in this session** — now dynamic |
| 11 | `index.html` line 30 | Placeholder `rhinoplasty nose reshaping…` | **Fixed in this session** |
| 12 | `index.html` lines 97,100 | Filter labels reference `(index_b)` and `(index_c)` | **Fixed in this session** |
| 13 | `router.py` q param examples | OpenAPI examples: "rhinoplasty", "anti aging face treatment", "plastic surgeon Los Angeles" | **Fixed in this session** |

## Final API shape (implemented)

```
GET /api/v1/search?q=...
  &filter_term=category:Electronics    # exact term (any field, repeated)
  &filter_term=in_stock:true           # boolean auto-cast
  &filter_gte=price:100                # numeric lower bound
  &filter_lte=price:500                # numeric upper bound
  &filter_gte=rating:4.0              # multiple range fields
```

All 13 violations resolved. No domain-specific code remains in the search path.

## Consequences

- Any new document CRUD endpoint must use `GenericDocumentRequest/GenericDocumentResponse`
- Any new filter added to the search API must use the generic key-value approach (after refactor)
- UI must detect value types at runtime (boolean, array, long string), never by field name
- OpenAPI examples must use placeholder domain: `"example query"`, `"my-index"`, etc.
