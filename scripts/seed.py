"""
Seed script — generate and index test documents into OpenSearch with semantic embeddings.

Usage:
    uv run python scripts/seed.py                              # defaults: 100 procedures, 200 doctors, 2000 reviews
    uv run python scripts/seed.py --procedures 500 --doctors 200 --reviews 10000
    uv run python scripts/seed.py --clear                      # delete indices before seeding
    uv run python scripts/seed.py --clear --procedures 0 --doctors 0 --reviews 0  # only clear
    uv run python scripts/seed.py --no-embeddings             # skip embedding generation (faster)
"""

from __future__ import annotations

import argparse
import os
import random
import uuid
from datetime import UTC, datetime, timedelta

from faker import Faker
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
from sentence_transformers import SentenceTransformer

fake = Faker()
random.seed(42)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ---------------------------------------------------------------------------
# OpenSearch connection
# ---------------------------------------------------------------------------

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
APP_ENV = os.getenv("APP_ENV", "development")

BULK_CHUNK_SIZE = 500


def get_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Index names
# ---------------------------------------------------------------------------


def index_name(domain: str) -> str:
    return f"{APP_ENV}_{domain}_v1"


PROCEDURES_INDEX = index_name("procedures")
DOCTORS_INDEX = index_name("doctors")
REVIEWS_INDEX = index_name("reviews")

# ---------------------------------------------------------------------------
# Domain data
# ---------------------------------------------------------------------------

PROCEDURE_CATALOG: list[dict] = [
    {
        "name": "Rhinoplasty",
        "category": "Facial",
        "body_area": "Nose",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (5000, 15000),
    },
    {
        "name": "Botox Injections",
        "category": "Facial",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (300, 1200),
    },
    {
        "name": "Facelift",
        "category": "Facial",
        "body_area": "Face",
        "surgical": True,
        "recovery_days": 21,
        "cost_range": (7000, 20000),
    },
    {
        "name": "Eyelid Surgery",
        "category": "Facial",
        "body_area": "Eyes",
        "surgical": True,
        "recovery_days": 10,
        "cost_range": (3000, 8000),
    },
    {
        "name": "Brow Lift",
        "category": "Facial",
        "body_area": "Forehead",
        "surgical": True,
        "recovery_days": 10,
        "cost_range": (3500, 8000),
    },
    {
        "name": "Chin Augmentation",
        "category": "Facial",
        "body_area": "Chin",
        "surgical": True,
        "recovery_days": 7,
        "cost_range": (2000, 5000),
    },
    {
        "name": "Cheek Augmentation",
        "category": "Facial",
        "body_area": "Cheeks",
        "surgical": True,
        "recovery_days": 7,
        "cost_range": (2500, 6000),
    },
    {
        "name": "Lip Augmentation",
        "category": "Facial",
        "body_area": "Lips",
        "surgical": False,
        "recovery_days": 1,
        "cost_range": (500, 2000),
    },
    {
        "name": "Dermal Fillers",
        "category": "Facial",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (600, 2500),
    },
    {
        "name": "Chemical Peel",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 5,
        "cost_range": (150, 3000),
    },
    {
        "name": "Microdermabrasion",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (100, 300),
    },
    {
        "name": "Laser Skin Resurfacing",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 7,
        "cost_range": (1000, 5000),
    },
    {
        "name": "Ultherapy",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (2000, 5000),
    },
    {
        "name": "Microneedling",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 3,
        "cost_range": (200, 700),
    },
    {
        "name": "IPL Photofacial",
        "category": "Skin",
        "body_area": "Face",
        "surgical": False,
        "recovery_days": 2,
        "cost_range": (300, 1000),
    },
    {
        "name": "Breast Augmentation",
        "category": "Breast",
        "body_area": "Breasts",
        "surgical": True,
        "recovery_days": 21,
        "cost_range": (5000, 12000),
    },
    {
        "name": "Breast Lift",
        "category": "Breast",
        "body_area": "Breasts",
        "surgical": True,
        "recovery_days": 21,
        "cost_range": (5000, 10000),
    },
    {
        "name": "Breast Reduction",
        "category": "Breast",
        "body_area": "Breasts",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (5000, 10000),
    },
    {
        "name": "Breast Reconstruction",
        "category": "Breast",
        "body_area": "Breasts",
        "surgical": True,
        "recovery_days": 42,
        "cost_range": (5000, 15000),
    },
    {
        "name": "Liposuction",
        "category": "Body",
        "body_area": "Abdomen",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (3000, 10000),
    },
    {
        "name": "Tummy Tuck",
        "category": "Body",
        "body_area": "Abdomen",
        "surgical": True,
        "recovery_days": 28,
        "cost_range": (6000, 15000),
    },
    {
        "name": "Body Contouring",
        "category": "Body",
        "body_area": "Body",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (5000, 20000),
    },
    {
        "name": "Brazilian Butt Lift",
        "category": "Body",
        "body_area": "Buttocks",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (5000, 12000),
    },
    {
        "name": "Arm Lift",
        "category": "Body",
        "body_area": "Arms",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (4000, 9000),
    },
    {
        "name": "Thigh Lift",
        "category": "Body",
        "body_area": "Thighs",
        "surgical": True,
        "recovery_days": 14,
        "cost_range": (5000, 10000),
    },
    {
        "name": "CoolSculpting",
        "category": "Body",
        "body_area": "Body",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (600, 4000),
    },
    {
        "name": "Hair Transplant",
        "category": "Hair",
        "body_area": "Scalp",
        "surgical": True,
        "recovery_days": 10,
        "cost_range": (4000, 15000),
    },
    {
        "name": "PRP Hair Treatment",
        "category": "Hair",
        "body_area": "Scalp",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (500, 2500),
    },
    {
        "name": "Laser Hair Removal",
        "category": "Skin",
        "body_area": "Body",
        "surgical": False,
        "recovery_days": 0,
        "cost_range": (200, 3000),
    },
    {
        "name": "Otoplasty",
        "category": "Facial",
        "body_area": "Ears",
        "surgical": True,
        "recovery_days": 10,
        "cost_range": (3000, 7000),
    },
]

SPECIALTIES = [
    "Plastic Surgeon",
    "Cosmetic Surgeon",
    "Dermatologist",
    "Facial Plastic Surgeon",
    "Oculoplastic Surgeon",
    "Reconstructive Surgeon",
]

CERTIFICATIONS = [
    "American Board of Plastic Surgery",
    "American Board of Dermatology",
    "American Board of Facial Plastic and Reconstructive Surgery",
    "American Board of Surgery",
    "Fellow of the American College of Surgeons",
    "International Society of Aesthetic Plastic Surgery",
]

CITIES = [
    ("New York", "NY"),
    ("Los Angeles", "CA"),
    ("Miami", "FL"),
    ("Beverly Hills", "CA"),
    ("Chicago", "IL"),
    ("Houston", "TX"),
    ("Dallas", "TX"),
    ("Phoenix", "AZ"),
    ("San Francisco", "CA"),
    ("Seattle", "WA"),
    ("Boston", "MA"),
    ("Atlanta", "GA"),
    ("Denver", "CO"),
    ("Las Vegas", "NV"),
    ("Nashville", "TN"),
]

WORTH_IT_CHOICES = ["Yes", "No", "Not Sure"]

PROCEDURE_TAGS: dict[str, list[str]] = {
    "Facial": ["anti-aging", "rejuvenation", "contouring", "symmetry", "facial-harmony"],
    "Skin": ["skin-tone", "texture", "wrinkles", "acne-scars", "glow", "rejuvenation"],
    "Breast": ["size", "shape", "symmetry", "lift", "reconstruction"],
    "Body": ["contouring", "weight-loss", "toning", "curves", "sculpting"],
    "Hair": ["hair-loss", "density", "hairline", "restoration"],
}

# ---------------------------------------------------------------------------
# Index mappings
# ---------------------------------------------------------------------------

_KNN_FIELD = {
    "type": "knn_vector",
    "dimension": EMBEDDING_DIM,
    "method": {
        "name": "hnsw",
        "space_type": "cosinesimil",
        "engine": "lucene",
    },
}

_KNN_SETTINGS = {"index.knn": True}

PROCEDURES_MAPPING = {
    "settings": _KNN_SETTINGS,
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "category": {"type": "keyword"},
            "body_area": {"type": "keyword"},
            "description": {"type": "text"},
            "is_surgical": {"type": "boolean"},
            "recovery_days": {"type": "integer"},
            "average_cost_usd": {"type": "integer"},
            "average_rating": {"type": "float"},
            "review_count": {"type": "integer"},
            "tags": {"type": "keyword"},
            "embedding": _KNN_FIELD,
        }
    },
}

DOCTORS_MAPPING = {
    "settings": _KNN_SETTINGS,
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "specialty": {"type": "keyword"},
            "city": {"type": "keyword"},
            "state": {"type": "keyword"},
            "years_experience": {"type": "integer"},
            "average_rating": {"type": "float"},
            "review_count": {"type": "integer"},
            "bio": {"type": "text"},
            "certifications": {"type": "keyword"},
            "procedures_performed": {"type": "keyword"},
            "embedding": _KNN_FIELD,
        }
    },
}

REVIEWS_MAPPING = {
    "settings": _KNN_SETTINGS,
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "procedure_id": {"type": "keyword"},
            "procedure_name": {"type": "keyword"},
            "doctor_id": {"type": "keyword"},
            "doctor_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "rating": {"type": "integer"},
            "title": {"type": "text"},
            "content": {"type": "text"},
            "date": {"type": "date"},
            "helpful_count": {"type": "integer"},
            "verified": {"type": "boolean"},
            "worth_it": {"type": "keyword"},
            "embedding": _KNN_FIELD,
        }
    },
}

# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def load_model() -> SentenceTransformer:
    print(f"Loading embedding model: {EMBEDDING_MODEL} (downloads on first run ~90MB)...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("  Model ready.")
    return model


def embed_texts(
    model: SentenceTransformer, texts: list[str], batch_size: int = 64
) -> list[list[float]]:
    vectors = model.encode(
        texts, batch_size=batch_size, show_progress_bar=True, normalize_embeddings=True
    )
    return vectors.tolist()


def procedure_text(doc: dict) -> str:
    tags = " ".join(doc.get("tags", []))
    return f"{doc['name']} {doc['body_area']} {doc['category']} {doc['description']} {tags}"


def doctor_text(doc: dict) -> str:
    procs = " ".join(doc.get("procedures_performed", []))
    certs = " ".join(doc.get("certifications", []))
    return f"{doc['name']} {doc['specialty']} {doc['bio']} {procs} {certs}"


def review_text(doc: dict) -> str:
    return f"{doc['title']} {doc['content']}"


def attach_embeddings(model: SentenceTransformer, docs: list[dict], text_fn) -> None:
    """Encode all docs in batch and attach embedding in-place."""
    texts = [text_fn(d) for d in docs]
    vectors = embed_texts(model, texts)
    for doc, vec in zip(docs, vectors, strict=True):
        doc["embedding"] = vec


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def generate_procedure(template: dict) -> dict:
    cost_min, cost_max = template["cost_range"]
    category = template["category"]
    tags = random.sample(
        PROCEDURE_TAGS.get(category, ["cosmetic"]),
        k=min(3, len(PROCEDURE_TAGS.get(category, ["cosmetic"]))),
    )
    return {
        "id": str(uuid.uuid4()),
        "name": template["name"],
        "category": category,
        "body_area": template["body_area"],
        "description": fake.paragraph(nb_sentences=random.randint(3, 6)),
        "is_surgical": template["surgical"],
        "recovery_days": template["recovery_days"],
        "average_cost_usd": random.randint(cost_min, cost_max),
        "average_rating": round(random.uniform(3.5, 5.0), 1),
        "review_count": random.randint(10, 2000),
        "tags": tags,
    }


def generate_doctor() -> dict:
    city, state = random.choice(CITIES)
    specialty = random.choice(SPECIALTIES)
    years = random.randint(5, 35)
    certs = random.sample(CERTIFICATIONS, k=random.randint(1, 3))
    procedures = random.sample([p["name"] for p in PROCEDURE_CATALOG], k=random.randint(3, 10))
    return {
        "id": str(uuid.uuid4()),
        "name": f"Dr. {fake.name()}",
        "specialty": specialty,
        "city": city,
        "state": state,
        "years_experience": years,
        "average_rating": round(random.uniform(3.8, 5.0), 1),
        "review_count": random.randint(5, 500),
        "bio": fake.paragraph(nb_sentences=random.randint(4, 8)),
        "certifications": certs,
        "procedures_performed": procedures,
    }


def generate_review(procedures: list[dict], doctors: list[dict]) -> dict:
    procedure = random.choice(procedures)
    doctor = random.choice(doctors)
    rating = random.choices([1, 2, 3, 4, 5], weights=[3, 5, 10, 30, 52])[0]
    date = datetime.now(UTC) - timedelta(days=random.randint(0, 365 * 5))
    return {
        "id": str(uuid.uuid4()),
        "procedure_id": procedure["id"],
        "procedure_name": procedure["name"],
        "doctor_id": doctor["id"],
        "doctor_name": doctor["name"],
        "rating": rating,
        "title": fake.sentence(nb_words=random.randint(5, 10)).rstrip("."),
        "content": " ".join(fake.paragraphs(nb=random.randint(2, 5))),
        "date": date.strftime("%Y-%m-%d"),
        "helpful_count": random.randint(0, 150),
        "verified": random.random() > 0.3,
        "worth_it": random.choices(WORTH_IT_CHOICES, weights=[60, 20, 20])[0],
    }


# ---------------------------------------------------------------------------
# Indexing helpers
# ---------------------------------------------------------------------------


def create_index(client: OpenSearch, name: str, mapping: dict, clear: bool) -> None:
    if clear and client.indices.exists(index=name):
        client.indices.delete(index=name)
        print(f"  Deleted index: {name}")
    if not client.indices.exists(index=name):
        client.indices.create(index=name, body=mapping)
        print(f"  Created index: {name}")
    else:
        print(f"  Index already exists (skipping create): {name}")


def bulk_index(client: OpenSearch, index: str, docs: list[dict]) -> tuple[int, int]:
    actions = [{"_index": index, "_id": doc["id"], "_source": doc} for doc in docs]
    success, errors = bulk(client, actions, chunk_size=BULK_CHUNK_SIZE, raise_on_error=False)
    return success, len(errors) if isinstance(errors, list) else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed OpenSearch with test data and semantic embeddings"
    )
    parser.add_argument(
        "--procedures", type=int, default=100, help="Number of procedures (default: 100)"
    )
    parser.add_argument("--doctors", type=int, default=200, help="Number of doctors (default: 200)")
    parser.add_argument(
        "--reviews", type=int, default=2000, help="Number of reviews (default: 2000)"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Delete and recreate indices before seeding"
    )
    parser.add_argument(
        "--no-embeddings", action="store_true", help="Skip embedding generation (faster, BM25 only)"
    )
    args = parser.parse_args()

    client = get_client()

    try:
        info = client.info()
        print(
            f"Connected to OpenSearch {info['version']['number']} at {OPENSEARCH_HOST}:{OPENSEARCH_PORT}"
        )
    except Exception as e:
        print(f"Failed to connect to OpenSearch: {e}")
        raise SystemExit(1) from e

    print(f"\nEnvironment: {APP_ENV}")
    print(f"Indices prefix: {APP_ENV}_*_v1")
    print(
        f"Embeddings: {'disabled (--no-embeddings)' if args.no_embeddings else f'enabled ({EMBEDDING_MODEL})'}\n"
    )

    # Load embedding model upfront (only if needed)
    model = None if args.no_embeddings else load_model()

    # Create indices
    print("\nSetting up indices...")
    create_index(client, PROCEDURES_INDEX, PROCEDURES_MAPPING, args.clear)
    create_index(client, DOCTORS_INDEX, DOCTORS_MAPPING, args.clear)
    create_index(client, REVIEWS_INDEX, REVIEWS_MAPPING, args.clear)

    # Generate and index procedures
    procedures: list[dict] = []
    if args.procedures > 0:
        print(f"\nGenerating {args.procedures} procedures...")
        catalog_cycle = PROCEDURE_CATALOG * (args.procedures // len(PROCEDURE_CATALOG) + 1)
        procedures = [generate_procedure(catalog_cycle[i]) for i in range(args.procedures)]
        if model:
            print("  Generating embeddings for procedures...")
            attach_embeddings(model, procedures, procedure_text)
        ok, err = bulk_index(client, PROCEDURES_INDEX, procedures)
        print(f"  Indexed: {ok} | Errors: {err}")
    else:
        resp = client.search(
            index=PROCEDURES_INDEX, body={"query": {"match_all": {}}, "size": 1000}
        )
        procedures = [hit["_source"] for hit in resp["hits"]["hits"]]
        print(f"\nUsing {len(procedures)} existing procedures for reviews")

    # Generate and index doctors
    doctors: list[dict] = []
    if args.doctors > 0:
        print(f"\nGenerating {args.doctors} doctors...")
        doctors = [generate_doctor() for _ in range(args.doctors)]
        if model:
            print("  Generating embeddings for doctors...")
            attach_embeddings(model, doctors, doctor_text)
        ok, err = bulk_index(client, DOCTORS_INDEX, doctors)
        print(f"  Indexed: {ok} | Errors: {err}")
    else:
        resp = client.search(index=DOCTORS_INDEX, body={"query": {"match_all": {}}, "size": 1000})
        doctors = [hit["_source"] for hit in resp["hits"]["hits"]]
        print(f"\nUsing {len(doctors)} existing doctors for reviews")

    # Generate and index reviews
    if args.reviews > 0 and procedures and doctors:
        print(f"\nGenerating {args.reviews} reviews...")
        reviews = [generate_review(procedures, doctors) for _ in range(args.reviews)]
        if model:
            print("  Generating embeddings for reviews...")
            attach_embeddings(model, reviews, review_text)
        ok, err = bulk_index(client, REVIEWS_INDEX, reviews)
        print(f"  Indexed: {ok} | Errors: {err}")
    elif args.reviews > 0:
        print("\nSkipping reviews — no procedures or doctors available")

    # Summary
    client.indices.refresh(index=f"{APP_ENV}_*_v1")
    print("\n--- Summary ---")
    for idx in [PROCEDURES_INDEX, DOCTORS_INDEX, REVIEWS_INDEX]:
        if client.indices.exists(index=idx):
            count = client.count(index=idx)["count"]
            print(f"  {idx}: {count:,} documents")


if __name__ == "__main__":
    main()
