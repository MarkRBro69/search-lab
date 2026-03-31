"""Smoke tests against a real OpenSearch cluster."""

from __future__ import annotations

import uuid

import pytest

from src.modules.search.application.search_params import SearchParams
from src.modules.search.infrastructure.repository import search_bm25
from src.shared.search_mode import SearchMode

pytestmark = pytest.mark.integration


def test_bm25_search_finds_indexed_document(opensearch_client: object) -> None:
    """Create a temporary index, index one doc, BM25 search returns it in hits; then delete index."""
    index_name = f"integration-smoke-{uuid.uuid4().hex}"
    doc_id = "smoke-doc-1"
    try:
        opensearch_client.indices.create(
            index=index_name,
            body={"mappings": {"properties": {"title": {"type": "text"}}}},
        )
        opensearch_client.index(
            index=index_name,
            id=doc_id,
            body={"title": "unique smoke phrase xyzzy"},
            refresh=True,
        )
        params = SearchParams(
            q="unique smoke phrase xyzzy",
            mode=SearchMode.BM25,
            index_key="all",
            size=5,
        )
        index_alias = {"all": index_name}
        bm25_fields = {"all": ["title"]}
        raw = search_bm25(opensearch_client, params, index_alias, bm25_fields)
        hits_obj = raw["hits"]
        assert isinstance(hits_obj, dict)
        inner = hits_obj.get("hits", [])
        assert isinstance(inner, list)
        ids = [str(h["_id"]) for h in inner if isinstance(h, dict)]
        assert doc_id in ids
    finally:
        opensearch_client.indices.delete(index=index_name, ignore=[404])
