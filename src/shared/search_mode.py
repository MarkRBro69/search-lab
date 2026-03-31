"""Shared search mode enum — used by search API, eval, and experiments."""

from __future__ import annotations

from enum import StrEnum


class SearchMode(StrEnum):
    BM25 = "bm25"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    RRF = "rrf"


__all__ = ["SearchMode"]
