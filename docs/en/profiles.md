# Connection profiles

## What is a connection profile?

A **connection profile** bundles everything Search Lab needs to talk to your stack:

- **OpenSearch** — host, port, TLS, and authentication
- **Embedding** — how query and document vectors are produced (local model or cloud)
- **Logical indices** — a map from **keys you choose** (e.g. `articles`, `products`) to **physical index names** in OpenSearch
- **BM25 fields** — per logical key, which text fields participate in keyword search (so the UI and API stay generic)

You can store **several** profiles and **activate** one at a time. Search, document CRUD, eval, and benchmarks all use the **active** profile.

## Logical indices and `all`

- Each **logical key** points to one OpenSearch index (name is up to you).
- The reserved key **`all`** means **search across every configured index** in that profile (combined search).

**Writes** (create / update / delete document) **must not** target **`all`** — you must pick a **specific** logical key so the service knows which index to update.

## OpenSearch settings

| Aspect | What you configure |
|--------|---------------------|
| **Host / port** | Where the cluster HTTP API is reachable |
| **`use_ssl`** | Whether HTTPS is used |
| **`auth_type`** | How to authenticate: **`none`**, **`basic`** (username + password), or **`aws_signature_v4`** (SigV4 signing; region and keys as required) |

Exact field names appear in the API and Swagger when creating or replacing a profile.

## Embedding backends

| Provider | Typical use |
|----------|-------------|
| **`local_sentence_transformers`** | Run a **model name** locally (e.g. configured via environment); good for offline dev |
| **`aws_bedrock`** | Use a **Bedrock model id**; may require **AWS credentials** and region in the profile |

The UI and API describe the embedding block using these provider values.

## Secrets policy

**Passwords, API keys, and AWS secrets are never returned** by read endpoints or list responses. After creation, the API only shows **non-secret** connection metadata (e.g. host, port, auth **type**, optional username without password).

When you **edit** a profile, you must **re-submit** credential fields as required by the API — the server does not echo old secrets back for you to copy.

## API reference

All paths use the prefix **`/api/v1`**.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/profiles` | List profiles (sanitised) |
| POST | `/api/v1/profiles` | Create profile |
| GET | `/api/v1/profiles/{profile_id}` | Get one profile (sanitised) |
| PUT | `/api/v1/profiles/{profile_id}` | Replace profile |
| DELETE | `/api/v1/profiles/{profile_id}` | Delete profile |
| POST | `/api/v1/profiles/{profile_id}/activate` | Activate (others deactivated) |
| POST | `/api/v1/profiles/{profile_id}/test` | Probe OpenSearch + embedding |

## UI (Settings tab)

In **Settings** you can:

- **Create** and **edit** profiles (OpenSearch + embedding + indices + BM25 fields)
- **Activate** the profile you want for Search and Experiments
- **Test** connectivity and see per-subsystem success/latency

The **header** shows the **active profile** so you always know which cluster and index map are in use.

---

[← User guide index](README.md) · [Русская версия](../ru/profiles.md)
