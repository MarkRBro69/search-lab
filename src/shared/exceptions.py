"""Domain exception hierarchy and stable API error codes."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Error codes (string constants — no magic strings in callers)
# ---------------------------------------------------------------------------

PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
ALGORITHM_NOT_FOUND = "ALGORITHM_NOT_FOUND"
TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
RUN_NOT_FOUND = "RUN_NOT_FOUND"
BENCHMARK_SIZE_LT_K = "BENCHMARK_SIZE_LT_K"

SEARCH_INVALID_MODE = "SEARCH_INVALID_MODE"
EVAL_METRIC_INCOMPLETE = "EVAL_METRIC_INCOMPLETE"
MISSING_REFERENCE = "MISSING_REFERENCE"

SEARCH_UNAVAILABLE = "SEARCH_UNAVAILABLE"
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"

NO_ACTIVE_PROFILE = "NO_ACTIVE_PROFILE"
PROFILE_UPDATE_FAILED = "PROFILE_UPDATE_FAILED"

INVALID_INDEX_KEY = "INVALID_INDEX_KEY"

EMBEDDING_MODEL_MISMATCH = "EMBEDDING_MODEL_MISMATCH"
UNKNOWN_EMBEDDING_PROVIDER = "UNKNOWN_EMBEDDING_PROVIDER"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base application error with HTTP mapping and stable `code` for clients."""

    def __init__(self, *, code: str, detail: str, status_code: int) -> None:
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ClientError(AppError):
    """4xx — client-side issue (bad input, not found, validation)."""


class NotFoundError(ClientError):
    """404 — resource does not exist."""

    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(code=code, detail=detail, status_code=404)


class InvalidInputError(ClientError):
    """400 — bad request."""

    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(code=code, detail=detail, status_code=400)


class UnprocessableEntityError(ClientError):
    """422 — semantic validation failure."""

    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(code=code, detail=detail, status_code=422)


class ServiceUnavailableError(AppError):
    """503 — upstream search or storage temporarily unavailable."""

    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(code=code, detail=detail, status_code=503)
