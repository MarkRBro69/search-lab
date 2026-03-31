# Session Log

---

## 2026-03-31 — Core search stability audit: fixes + full test coverage

**Applied:**
- LOCAL `src/modules/search/application/search_service.py` — `_parse_hits`: `id` always normalized to `str`
- LOCAL `src/modules/search/application/eval_service.py` — removed redundant `str()` cast in `evaluate`; fixed `except (TypeError, ValueError)` syntax
- LOCAL `src/modules/search/application/search_params.py` — `__post_init__` validates `bm25_weight + knn_weight == 1.0` for HYBRID mode
- LOCAL `src/modules/search/infrastructure/repository.py` — `search_bm25/knn/wide`: `TransportError` → `ServiceUnavailableError`
- LOCAL `src/modules/experiments/domain/models.py` — `Algorithm`: `model_validator(mode="after")` for weight sum validation
- LOCAL `src/modules/experiments/application/experiments_service.py` — `size < k` → `InvalidInputError`; missing IDs → `NotFoundError`; logger `operation` fixed to `"execute_benchmark"`; `_compute_result` hits annotated as `list[dict[str, object]]`
- LOCAL `src/shared/exceptions.py` — added `BENCHMARK_SIZE_LT_K` constant
- LOCAL `pyproject.toml` — `integration` marker + `-m "not integration"` in addopts
- LOCAL `tests/unit/modules/search/application/test_eval_service.py` — edge cases: `k=0`, duplicates, `|R|>k`, MRR with no relevant
- LOCAL `tests/unit/modules/search/application/test_search_service.py` — int `_id` → str `id` normalization
- LOCAL `tests/unit/modules/search/application/test_search_params.py` — hybrid weight validation
- LOCAL `tests/unit/modules/search/infrastructure/test_repository.py` — `TransportError` → `ServiceUnavailableError` for 4 search functions
- LOCAL `tests/unit/modules/experiments/domain/test_models.py` — Algorithm weight validation
- LOCAL `tests/unit/modules/experiments/application/test_experiments_service.py` — `size<k`, `NotFoundError` (algo+template), error propagation without `save_run`, happy path
- LOCAL `tests/unit/modules/experiments/infrastructure/test_repository.py` — NEW: mongo round-trip + CRUD (was zero coverage)
- LOCAL `tests/integration/conftest.py` — NEW: OpenSearch + MongoDB fixtures with `integration` marker
- LOCAL `tests/integration/test_search_smoke.py` — NEW: BM25 smoke test
- LOCAL `.cursor/rules/experiments-patterns.mdc` — added Validation Rules section (weights, ID normalization, TransportError)
- LOCAL `.cursor/rules/opensearch-patterns.mdc` — added TransportError pattern for search functions
- LOCAL `.cursor/rules/architecture.mdc` — added Test Coverage Non-Negotiable section

**Result:** 151 unit tests passing (was ~100); 0 pre-existing test regressions

---

## 2026-03-31 — Bug fixes: benchmark crash, explain toggle, rank_eval metrics, template multiselect

**Applied:**
- LOCAL `src/modules/experiments/domain/models.py` — `AlgorithmFilters` refactored to domain-agnostic `filter_term/gte/lte`; removed stale domain-specific fields
- LOCAL `src/modules/experiments/application/experiments_service.py` — `_algo_to_params` updated to use new generic filters
- LOCAL `src/modules/search/infrastructure/repository.py` — `_resolve_index` / `_bm25_field_list` updated to expand comma-joined logical keys (template multiselect)
- LOCAL `src/modules/search/presentation/schemas.py` — `RankEvalRequest.metric` removed `ndcg` and `expected_reciprocal_rank` (Elasticsearch-only, not supported by OpenSearch)
- LOCAL `static/js/app.js` — `onExplainToggle()` now re-fetches from server when turning ON; re-renders from cache when turning OFF
- LOCAL `static/index.html` — `tmplIndex` select changed to `multiple`; rank_eval metric dropdown cleaned
- LOCAL `tests/unit/` — 13 new regression tests; fixed 3 stale tests with wrong `Algorithm.index` / `k=` args
- LOCAL `.cursor/rules/opensearch-patterns.mdc` — added `_rank_eval` unsupported metrics note (auto-applied)
- LOCAL `.cursor/rules/experiments-patterns.mdc` — fixed stale `Algorithm` class doc, added `AlgorithmFilters` domain-agnostic constraint
- LOCAL `.cursor/rules/agent-workflow.mdc` — added "Read terminal output" row to Tool Priority table

**Skipped:** none

---

## 2026-03-30 — Search core logic audit + unit test coverage (75 tests)

**Applied:**
- LOCAL `src/modules/search/application/eval_service.py` — фикс 2 аудит-проблем: `dict[index_key]` → проверка + `InvalidInputError`; `float(metric_score)` → try/except + `UnprocessableEntityError`
- LOCAL `tests/unit/modules/search/conftest.py` — создан: общие фикстуры `mock_os_client`, `mock_embed`, `index_alias`, `bm25_fields_by_key`
- LOCAL `tests/unit/modules/search/infrastructure/test_repository.py` — создан: 30 unit-тестов (`_resolve_index`, `build_filters`, `build_bm25_query`, `_bm25_body`, `_knn_body`, `_extract_*`, all search/get/index/delete/explain/rank_eval_native)
- LOCAL `tests/unit/modules/search/application/test_indexing_service.py` — создан: 8 тестов (`_serialize`, `_embedding_source_text`, create/get/update/delete document)
- LOCAL `tests/unit/modules/search/application/test_eval_service.py` — добавлены: `evaluate()`, `rank_eval()` тесты (успех, ошибки, неизвестный ключ)
- LOCAL `tests/unit/modules/search/application/test_search_service.py` — добавлен `explain_document_async`; исправлены моки hybrid/rrf
- LOCAL `tests/unit/modules/search/application/test_search_service_helpers.py` — добавлены edge cases: `_minmax` при равных скорах, пустые списки в `_hybrid_combine`/`_rrf_combine`
- LOCAL `.cursor/rules/fastapi-conventions.mdc` — добавлен anti-pattern: `dict[user_key]` без проверки и `float(untrusted)` без try/except → непойманные 500

**Skipped:** none

---

## 2026-03-30 — Full codebase audit and systematic fix (18 issues across 5 task groups)

**Applied:**
- LOCAL `src/shared/search_mode.py` — создан: `SearchMode(str, StrEnum)` — единый источник режимов поиска
- LOCAL `src/shared/infrastructure/logging.py` — создан: `configure_logging()` с ConsoleRenderer/JSONRenderer по `APP_ENV`
- LOCAL `src/shared/exceptions.py` — добавлены коды: `PROFILE_NOT_FOUND`, `ALGORITHM_NOT_FOUND`, `TEMPLATE_NOT_FOUND`, `RUN_NOT_FOUND`, `EMBEDDING_MODEL_MISMATCH`, `UNKNOWN_EMBEDDING_PROVIDER`
- LOCAL `src/shared/infrastructure/embedding.py` — удалён legacy-дубликат (пакет `embedding/` — единственный источник)
- LOCAL `src/modules/profiles/presentation/router.py` — все `HTTPException(404)` → `NotFoundError`
- LOCAL `src/modules/experiments/presentation/router.py` — все `HTTPException(404)` → `NotFoundError`; убран прямой импорт из infrastructure
- LOCAL `src/modules/experiments/application/experiments_service.py` — добавлен `get_template()` как фасад
- LOCAL `src/main.py` — `HealthResponse` Pydantic-модель; `configure_logging()` первым; `bind(module,operation)` в lifespan/handler
- LOCAL `src/modules/profiles/application/profiles_service.py` — нейтральные ключи `index_a/b/c`; `bind(module,operation)` в логах
- LOCAL `src/modules/search/application/search_params.py` — `mode: SearchMode`
- LOCAL `src/modules/search/application/eval_service.py` — `RankEvalResult` TypedDict; типизированный `rank_eval`
- LOCAL `src/modules/search/presentation/eval_router.py` — убраны все `# type: ignore`
- LOCAL `src/modules/search/presentation/document_schemas.py` — удалён мёртвый блок `DOC_TYPES/CREATE_SCHEMA/RESPONSE_SCHEMA`
- LOCAL `src/shared/infrastructure/embedding/factory.py` — `ValueError` → `InvalidInputError`
- LOCAL `static/js/app.js`, `static/css/app.css`, `static/index.html` — нейтральные индекс-ключи (index_a/b/c)
- LOCAL `scripts/seed.py`, `scripts/semantic_search_demo.py` — нейтральные индекс-ключи
- LOCAL `tests/unit/modules/**` — 8 новых файлов unit-тестов (~45 test-функций)
- LOCAL `.cursor/rules/experiments-patterns.mdc` — исправлен тип `mode` и комментарий `index`
- LOCAL `.cursor/rules/fastapi-conventions.mdc` — ужесточено правило: HTTPException запрещён для 4xx
- LOCAL `.cursor/rules/logging.mdc` — добавлено правило `request_id="-"` для non-HTTP контекстов
- LOCAL `docs/decisions/ADR-0005-search-mode-enum.md` — создан: решение о `SearchMode` как shared StrEnum

**Skipped:** none

---

## 2026-03-30 — UI refactoring, dynamic indices, error handling audit

**Applied:**
- LOCAL `static/index.html` — тонкая оболочка (~307 строк); inline `<style>` и `<script>` вынесены
- LOCAL `static/css/app.css` — создан (250 строк); весь CSS + `.settings-main { max-width: 640px }`
- LOCAL `static/js/app.js` — создан (1243 строки); вся логика + `refreshActiveProfileIndices`, `renderCollectionButtons`, `populateExperimentIndexSelects`, `resolveCardVariant`, `renderGenericSourceCard`; динамические кнопки коллекций из активного профиля
- LOCAL `src/shared/exceptions.py` — создан: `AppError`, `ClientError`, `NotFoundError`, `InvalidInputError`, `UnprocessableEntityError`, `ServiceUnavailableError` + строковые коды ошибок
- LOCAL `src/main.py` — обработчики `ServiceUnavailableError`, `AppError`, глобальный 500
- LOCAL `src/modules/search/application/search_service.py` — `ValueError` → `InvalidInputError`
- LOCAL `src/modules/search/application/eval_service.py` — `RuntimeError` → `UnprocessableEntityError`
- LOCAL `src/modules/experiments/application/experiments_service.py` — `ValueError` → `InvalidInputError` с отдельными кодами
- LOCAL `src/modules/search/infrastructure/repository.py` — убран `bare except Exception`; `NotFoundError` vs `ServiceUnavailableError`
- LOCAL `src/modules/profiles/presentation/deps.py` — HTTP 500 → `InvalidInputError(NO_ACTIVE_PROFILE)`
- LOCAL `src/modules/profiles/presentation/router.py` — `datetime` из `TYPE_CHECKING` → runtime import (`# noqa: TC003`); `HTTPException(500)` → `ServiceUnavailableError`
- LOCAL `src/modules/profiles/domain/models.py` — `@model_validator(mode='before')` для обратной совместимости с плоским форматом MongoDB
- LOCAL `.cursor/rules/fastapi-conventions.mdc` — обновлена секция Error Handling (иерархия исключений, схема ответов, антипаттерн Pydantic v2 + TYPE_CHECKING)
- LOCAL `.cursor/rules/architecture.mdc` — добавлено описание `src/shared/exceptions.py`
- LOCAL `AGENTS.md` — добавлен constraint про схему ошибок
- LOCAL `docs/decisions/ADR-0004-exception-hierarchy.md` — создан: решение о доменной иерархии исключений

**Skipped:** нет

---

## 2026-03-30 — Connection Profiles, UI redesign, benchmark metrics matrix

**Applied:**
- LOCAL `src/modules/profiles/` — создан новый модуль: ConnectionProfile (MongoDB CRUD, активация, кэш клиентов по profile_id, local/Bedrock embedding factory)
- LOCAL `src/shared/infrastructure/embedding/types.py` — EmbeddingConfig, EmbeddingProvider вынесены в shared (anti-circular)
- LOCAL `src/modules/search/` — search_service, repository, роутеры переведены на explicit index_alias + embed из активного профиля
- LOCAL `src/modules/experiments/` — execute_benchmark снимает снапшот (client, index_alias, embed) до N×M матрицы
- LOCAL `static/index.html` — Settings tab с Profile Management UI (CRUD + активация, условные поля auth_type/provider); сайдбар 360px + 6 секций; таблица экспериментов алгоритмы × 7 метрик из run.summary
- LOCAL `project-overview.mdc` — добавлен profiles модуль, boto3/requests-aws4auth в стек
- LOCAL `AGENTS.md` — profiles/ в Module Boundaries и Directory Layout; констрейнт про секреты в API
- LOCAL `docs/decisions/ADR-0003-connection-profiles.md` — создан: решение о Connection Profiles и размещении EmbeddingConfig в shared

**Skipped:** нет

Automatic log of knowledge updates applied per session.
Maintained by the `knowledge-update` skill. Newest entries at the top.

---

## 2026-03-29 — Added Pre-Stage 0: task decomposition rule

**Applied:**
- LOCAL `.cursor/rules/agent-workflow.mdc` — добавлен раздел "Task Decomposition (Pre-Stage 0)": сложные запросы с несколькими независимыми задачами разбиваются до Stage 1, каждая получает отдельный полный pipeline
- LOCAL `.cursor/rules/agent-workflow.mdc` — обновлён Response Template: показывает шаблон декомпозиции и повторение pipeline для каждой задачи
- LOCAL `AGENTS.md` — описание `agent-workflow.mdc` обновлено: упомянут Pre-Stage 0

**Skipped:** нет

---

## 2026-03-29 — Stage 5: pipeline deviation policy + knowledge update

**Applied:**
- LOCAL `.cursor/rules/agent-workflow.mdc` — добавлен раздел "Pipeline Deviation Policy": отклонение от pipeline требует явного подтверждения пользователя перед любым сокращением стадий
- LOCAL `.cursor/rules/agent-workflow.mdc` — уточнена формулировка "Skip to implementation directly (без approval)"
- LOCAL `AGENTS.md` — обновлено описание `agent-workflow.mdc` в Rules Map: упомянут Pipeline Deviation Policy

**Skipped:** нет

---

## 2026-03-29 — Full project audit + 7-task parallel fix sprint

**Applied:**
- LOCAL `src/modules/search/api.py` — добавлен публичный экспорт `search`, `SearchParams`, `ndcg_at_k`, `mrr`, `precision_at_k`, `recall_at_k` (устранено нарушение границ модулей)
- LOCAL `src/modules/experiments/application/experiments_service.py` — импорты переведены с `search.application.*` на `src.modules.search.api`
- LOCAL `src/modules/search/application/search_service.py` — `get_event_loop` → `get_running_loop` (×2)
- LOCAL `src/modules/search/application/eval_service.py` — `get_event_loop` → `get_running_loop` (×1)
- LOCAL `src/modules/search/application/indexing_service.py` — `get_event_loop` → `get_running_loop` (×4)
- LOCAL `src/shared/infrastructure/embedding.py` — `get_event_loop` → `get_running_loop` (×1)
- LOCAL `src/modules/experiments/domain/models.py` — `datetime.utcnow` → `datetime.now(UTC)` (×3)
- LOCAL `src/modules/search/presentation/schemas.py` — убран `Any`, введён `DocumentField` type alias
- LOCAL `src/modules/search/presentation/document_schemas.py` — убран `Any`, введён `DocumentField` type alias
- LOCAL `src/modules/search/infrastructure/repository.py` — добавлено `logger.warning` в `except Exception` блоки `get_document` и `delete_document`
- LOCAL `.cursor/rules/opensearch-patterns.mdc` — sync client + run_in_executor паттерн, реальные query builders, index naming
- LOCAL `.cursor/rules/experiments-patterns.mdc` — `_COL_*` константы, `_to_mongo`/`_from_mongo` паттерн
- LOCAL `.cursor/rules/fastapi-conventions.mdc` — Annotated DI, function-based services, реальный lifespan
- GLOBAL `~/.cursor/skills/opensearch-patterns/SKILL.md` — наполнен: sync+executor, BM25/KNN/hybrid/RRF паттерны, антипаттерны
- GLOBAL `~/.cursor/skills/fastapi-patterns/SKILL.md` — наполнен: Annotated DI, lifespan, middleware, inline schemas
- GLOBAL `~/.cursor/skills/motor-mongodb/SKILL.md` — наполнен: id↔_id маппинг, CRUD паттерны, проекции

**Skipped:** написание тестов (запланировано отдельно)

---

## 2026-03-29 — Built global skills system (agent-init + knowledge-update)

**Applied:**
- GLOBAL `~/.cursor/skills/knowledge-update/SKILL.md` — created: session log, auto-apply threshold, templates sync, global/local boundary
- GLOBAL `~/.cursor/skills/agent-init/SKILL.md` — created: project initialization wizard with audit mode, technology scan, skill health review
- GLOBAL `~/.cursor/skills/agent-init/templates/` — created: AGENTS.md, communication, project-overview, architecture, tooling, agent-workflow, testing, logging, git-conventions
- LOCAL `.cursor/rules/agent-workflow.mdc` — Stage 5 added as mandatory with explicit 6-question checklist
- LOCAL `AGENTS.md` — added Global Skills section (knowledge-update, agent-init)

**Skipped:** systematic-debugging skill (user decided not to add at this time)
