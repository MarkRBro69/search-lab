# Search Lab

**Search Lab** is a FastAPI-based platform for comparing OpenSearch search algorithms. You define algorithm configurations, maintain a library of queries with ground-truth relevance labels, and run **N × M** benchmarks to compare quality (NDCG@K, MRR, precision, recall, latency, score separation) side by side. Results are stored for historical comparison.

Use the web UI for day-to-day search and experiments, or call the HTTP API under `/api/v1`. Interactive API documentation is available at `/docs` when the app is running.

## Documentation

- **User documentation (EN):** [docs/en/README.md](docs/en/README.md)
- **Пользовательская документация (RU):** [docs/ru/README.md](docs/ru/README.md)
- **Developer setup:** [docs/developer-setup.md](docs/developer-setup.md)
