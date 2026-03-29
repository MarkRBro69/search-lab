# Настройка окружения разработчика

**Search Lab** — платформа для тестирования поисковых алгоритмов на OpenSearch.
Это руководство поможет тебе запустить проект локально и персонализировать поведение LLM-агентов.

## Требования

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — установи глобально
- Docker Desktop (или Docker Engine + docker-compose)
- Cursor IDE

## Установка проекта

```powershell
# 1. Клонировать репозиторий
git clone <repo-url>
cd new_search

# 2. Установить зависимости (uv создаёт .venv автоматически)
uv sync --all-extras

# 3. Установить pre-commit хуки
uv run pre-commit install

# 4. Скопировать файл окружения
Copy-Item .env.example .env
# Открыть .env и заполнить нужные значения
```

## Запуск инфраструктуры

```powershell
# Минимум для работы (OpenSearch + MongoDB нужны оба)
docker-compose up -d opensearch mongodb

# Полный стек (+ Dashboards + приложение в контейнере)
docker-compose up -d

# Проверить статус
docker-compose ps
```

## Запуск приложения

```powershell
make dev
# или
uv run uvicorn src.main:app --reload
```

Приложение будет доступно на `http://localhost:8000`.
Swagger UI: `http://localhost:8000/docs`.

---

## Персональный профиль агента

Каждый разработчик может настроить поведение LLM-агентов под себя: язык общения, синтаксис команд, уровень подтверждений.

### Как создать профиль

**Шаг 1.** Скопируй шаблон:

```powershell
Copy-Item .cursor\templates\developer-profile.mdc .cursor\rules\local\my-profile.mdc
```

**Шаг 2.** Открой `.cursor/rules/local/my-profile.mdc` и заполни поля:

```markdown
---
description: Personal developer profile
alwaysApply: true
---

# Developer Profile

- OS: windows
- Shell: powershell
- Communication language: ru
- Terminal command style: always use PowerShell syntax in suggestions
- Confirmation: yes
- Verbosity: concise
```

**Шаг 3.** Сохрани файл. Cursor подхватит его автоматически в следующей сессии.

> Файл гитигнорируется — в репозиторий не попадёт.

### Описание полей

| Поле | Значения | Эффект |
|---|---|---|
| `OS` | `windows`, `macos`, `linux` | Агент знает особенности платформы |
| `Shell` | `powershell`, `bash`, `zsh` | Все команды в терминале — в нужном синтаксисе |
| `Communication language` | `ru`, `en` | Язык ответов, комментариев, коммитов |
| `Confirmation` | `yes`, `no` | Спрашивать ли подтверждение перед многошаговыми планами |
| `Verbosity` | `concise`, `detailed` | Краткие или развёрнутые объяснения |

### Примеры

**Windows / PowerShell / Русский:**
```markdown
- OS: windows
- Shell: powershell
- Communication language: ru
- Terminal command style: always use PowerShell syntax
- Confirmation: yes
- Verbosity: concise
```

**macOS / zsh / English:**
```markdown
- OS: macos
- Shell: zsh
- Communication language: en
- Terminal command style: always use bash/zsh syntax
- Confirmation: no
- Verbosity: detailed
```

---

## Структура правил агентов

Все правила в `.cursor/rules/` автоматически применяются агентами:

| Файл | Когда применяется |
|---|---|
| `project-overview.mdc` | Всегда |
| `architecture.mdc` | Всегда |
| `agent-workflow.mdc` | Всегда |
| `tooling.mdc` | Всегда |
| `git-conventions.mdc` | Всегда |
| `logging.mdc` | Всегда |
| `fastapi-conventions.mdc` | При работе с `.py` файлами |
| `testing.mdc` | При работе с `tests/` |
| `opensearch-patterns.mdc` | При работе с `src/modules/search/infrastructure/` |
| `llm-agent-integration.mdc` | При работе с `src/modules/agents/` |
| `local/my-profile.mdc` | Всегда (личный, гитигнорируется) |
