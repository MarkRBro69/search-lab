"""
Demo script for semantic search using KNN in OpenSearch.

Usage:
    uv run python scripts/semantic_search_demo.py "face lifting procedure"
    uv run python scripts/semantic_search_demo.py "experienced surgeon in New York" --index doctors
    uv run python scripts/semantic_search_demo.py "great results no side effects" --index reviews
"""

from __future__ import annotations

import argparse
import os

from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer

APP_ENV = os.getenv("APP_ENV", "development")
PROCEDURES_INDEX = f"{APP_ENV}_procedures_v1"
DOCTORS_INDEX = f"{APP_ENV}_doctors_v1"
REVIEWS_INDEX = f"{APP_ENV}_reviews_v1"

INDEX_MAP = {
    "procedures": PROCEDURES_INDEX,
    "doctors": DOCTORS_INDEX,
    "reviews": REVIEWS_INDEX,
}

SOURCE_FIELDS = {
    "procedures": ["name", "category", "body_area", "description", "average_rating", "tags"],
    "doctors": ["name", "specialty", "city", "state", "average_rating", "bio"],
    "reviews": ["title", "content", "rating", "procedure_name", "doctor_name", "worth_it"],
}


def get_client() -> OpenSearch:
    return OpenSearch(
        hosts=[
            {
                "host": os.getenv("OPENSEARCH_HOST", "localhost"),
                "port": int(os.getenv("OPENSEARCH_PORT", "9200")),
            }
        ],
        use_ssl=False,
        verify_certs=False,
        http_compress=True,
    )


def semantic_search(client: OpenSearch, query: str, index_key: str, k: int = 5) -> None:
    print("\nLoading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    vector = model.encode(query, normalize_embeddings=True).tolist()

    index = INDEX_MAP[index_key]
    fields = SOURCE_FIELDS[index_key]

    body = {
        "size": k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": vector,
                    "k": k,
                }
            }
        },
        "_source": fields,
    }

    print(f"\nSemantic search in [{index}]")
    print(f'Query: "{query}"')
    print("-" * 60)

    resp = client.search(index=index, body=body)
    hits = resp["hits"]["hits"]

    if not hits:
        print("No results found.")
        return

    for i, hit in enumerate(hits, 1):
        score = hit["_score"]
        src = hit["_source"]
        print(f"\n#{i} score={score:.4f}")
        for field in fields:
            val = src.get(field)
            if val is None:
                continue
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val[:5])
            elif isinstance(val, str) and len(val) > 120:
                val = val[:120] + "..."
            print(f"  {field}: {val}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search demo")
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "--index",
        choices=["procedures", "doctors", "reviews"],
        default="procedures",
        help="Index to search (default: procedures)",
    )
    parser.add_argument("--k", type=int, default=5, help="Number of results (default: 5)")
    args = parser.parse_args()

    client = get_client()
    semantic_search(client, args.query, args.index, args.k)


if __name__ == "__main__":
    main()
