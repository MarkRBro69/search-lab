# ADR-0001: Clean Architecture + Modular Monolith + Tactical DDD

## Status

Accepted

## Context

We are building a search service that will grow in complexity over time:
- Multiple search strategies (full-text, semantic, hybrid)
- LLM agent integration with evolving tool interfaces
- Potential need to extract modules into separate services as the system scales

We needed an architecture that:
1. Keeps code testable without requiring real infrastructure (OpenSearch, LLM)
2. Allows modules to evolve independently without tight coupling
3. Scales from simple use cases to complex domain logic as needed
4. Enables future extraction of modules into microservices with minimal refactoring

## Decision

**Clean Architecture** inside a **Modular Monolith**, with **Tactical DDD** applied selectively.

### Clean Architecture (per module)

Each module is divided into layers with a strict inward dependency rule:

```
Presentation → Application → [Domain] ← Infrastructure
```

- `Presentation`: FastAPI routers and Pydantic schemas
- `Application`: use cases, commands, queries — orchestrates domain and infrastructure
- `Domain` (optional): entities, value objects, domain events — pure Python, zero framework deps
- `Infrastructure`: concrete implementations (OpenSearch repos, LLM client adapters)

### Modular Monolith

All modules live in `src/modules/{name}/` as independent vertical slices.
Each module exposes a public interface via `api.py` — no other module imports its internals.

### Tactical DDD (selective)

The `domain/` layer is added only when a module develops non-trivial business logic
(complex invariants, domain events, multiple aggregates). For simple query modules, it is skipped.

## Alternatives Considered

### Simple layered architecture (controllers → services → repositories)

**Rejected** because: leads to fat services with mixed concerns, testing requires full stack setup,
no clear path to extracting modules.

### Full microservices from the start

**Rejected** because: premature at this stage — adds operational complexity (service discovery,
distributed tracing, inter-service auth) before the domain is well understood.
We can extract modules later when boundaries are proven stable.

### CQRS + Event Sourcing

**Rejected** because: too complex for initial scope. May revisit for the agents module
if event-driven patterns become necessary.

## Consequences

**Positive:**
- Use cases are fully testable without any infrastructure (mock repos via DI)
- Module boundaries are explicit — safe to refactor or extract independently
- `domain/` layer can be added incrementally as logic grows
- LLM agents working on the codebase have clear, consistent rules to follow

**Negative:**
- More boilerplate for simple CRUD operations (use case class instead of direct repo call)
- Developers must understand layer responsibilities to place code correctly

**Mitigations:**
- `architecture.mdc` rule enforces placement for LLM agents
- Domain layer is explicitly optional to avoid over-engineering simple modules
