# Session Log

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
