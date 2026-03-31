# Public interface for the search module
from __future__ import annotations

from src.modules.search.application.eval_service import (
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from src.modules.search.application.search_params import SearchParams
from src.modules.search.application.search_service import search
from src.modules.search.presentation.document_router import router as document_router
from src.modules.search.presentation.eval_router import router as eval_router
from src.modules.search.presentation.router import router as search_router
from src.shared.search_mode import SearchMode

__all__ = [
    "SearchMode",
    "SearchParams",
    "document_router",
    "eval_router",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "search",
    "search_router",
]
