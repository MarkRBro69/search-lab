# Search Lab — User Guide

## What this is

Search Lab helps you run and compare search algorithms on **OpenSearch** using a single workflow: search in the UI or API, score results against known relevant documents, and run **benchmark matrices** (many algorithms × many queries) with consistent metrics. It is built for repeatable evaluation, not for production search serving.

## Who it's for

Researchers, search engineers, and anyone who needs to compare **BM25**, **semantic (vector)**, **hybrid**, and **RRF** setups on the same data and query set.

## Contents

- [Getting started](getting-started.md) — environment, first run, first search, search modes
- [Metrics](metrics.md) — application metrics vs native OpenSearch `_rank_eval`
- [Connection profiles](profiles.md) — OpenSearch, embeddings, indices, API and Settings UI
- [Experiments](experiments.md) — algorithms, query templates, benchmarks, API and UI

## Related

- [Developer setup](../developer-setup.md) — full local install, tooling, agent profiles
- **OpenAPI / Swagger** — when the app is running: `http://localhost:8000/docs` (adjust host/port as needed)
- [Architecture decisions](../decisions/) — ADRs and design notes for contributors

## Language

This guide is in English. A Russian version is available: [Руководство пользователя (RU)](../ru/README.md).
