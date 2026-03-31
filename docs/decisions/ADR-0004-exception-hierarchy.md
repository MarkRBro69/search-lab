# ADR-0004: Domain Exception Hierarchy and Centralized Error Handling

**Date:** 2026-03-30
**Status:** Accepted

## Context

Endpoints were returning generic HTTP 500 "Internal server error" for all unhandled
exceptions (ValueError, RuntimeError, bare OpenSearch errors). Clients had no way to
distinguish configuration errors from service outages or validation problems.
The repository layer was swallowing real OpenSearch errors inside bare `except Exception`
blocks and returning `None`, causing misleading "not found" responses to clients.

## Decision

Introduce a domain exception hierarchy in `src/shared/exceptions.py`:
- `AppError` — base class with `code: str` and `detail: str`
- `ClientError(AppError)` — 4xx client errors
  - `NotFoundError` (404), `InvalidInputError` (400), `UnprocessableEntityError` (422)
- `ServiceUnavailableError(AppError)` — 503 for OpenSearch/MongoDB infrastructure failures

String error codes are defined as module-level constants (no magic strings):
`SEARCH_INVALID_MODE`, `DOCUMENT_NOT_FOUND`, `NO_ACTIVE_PROFILE`, `SEARCH_UNAVAILABLE`, etc.

Register centralized handlers in `src/main.py`:
- `ServiceUnavailableError` → 503, fixed sanitized `detail`, `code` field
- `AppError` → correct `status_code` from exception, body `{"detail": str, "code": str}`
- Generic `Exception` → 500 `{"detail": "Internal server error"}` only (no code, no raw text)

Application and domain layers raise domain exceptions only (no FastAPI imports).
Presentation layer catches infrastructure exceptions (e.g. `TransportError`) and wraps
them in `ServiceUnavailableError` before they reach the centralized handler.

## Consequences

- 4xx responses are predictable and machine-readable: `{"detail": str, "code": str}`
- 500 responses never leak stack traces or raw upstream messages (OpenSearch, MongoDB)
- OpenSearch connection failures surface as 503, not misleading 404 or generic 500
- Adding new error types: subclass `ClientError` or `AppError` + register handler if needed
- Application/domain layers have no dependency on FastAPI — easier to test in isolation
