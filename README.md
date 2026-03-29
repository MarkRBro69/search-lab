# Search Lab

Платформа для тестирования и сравнения алгоритмов поиска на базе OpenSearch.

## Цель проекта

**Search Lab** — это инструмент для исследователей и инженеров, который позволяет:

- Сравнивать алгоритмы поиска (BM25, семантический, гибридный, RRF) по единым метрикам IR
- Строить библиотеку запросов с ground-truth разметкой и многократно использовать её
- Запускать бенчмарки вида **N алгоритмов × M запросов** и получать итоговую таблицу метрик
- Анализировать качество ранжирования: NDCG@K, MRR, Precision@K, Recall@K, разделение оценок

## Ключевые возможности

### Алгоритмы поиска

| Режим | Алгоритм | Когда использовать |
|---|---|---|
| `bm25` | TF-IDF keyword search | Точные названия, артикулы |
| `semantic` | KNN vector search (all-MiniLM-L6-v2) | Описательные / расплывчатые запросы |
| `hybrid` | BM25 × вес + KNN × вес | Общее использование (рекомендован) |
| `rrf` | Reciprocal Rank Fusion | Ансамблевое ранжирование без ручных весов |

### Метрики оценки

| Метрика | Описание |
|---|---|
| NDCG@K | Нормализованный дисконтированный кумулятивный gain |
| MRR | Mean Reciprocal Rank — 1/позиция первого релевантного результата |
| Precision@K | Доля релевантных в топ-K |
| Recall@K | Доля найденных из всех релевантных |
| Score Separation | Разрыв оценок между релевантными и нерелевантными — диагностика ранжировщика |
| Latency (ms) | Время выполнения каждого поискового запроса |

### Рабочий процесс

```
1. Создать алгоритм  →  POST /experiments/algorithms
   (режим, веса, фильтры, индекс)

2. Создать шаблоны запросов  →  POST /experiments/templates
   (запрос + список ground-truth ID)

3. Запустить бенчмарк  →  POST /experiments/benchmark
   (N алгоритмов × M шаблонов → матрица метрик)

4. Проанализировать результаты  →  GET /experiments/benchmark/{id}
   (NDCG, MRR, latency, score separation на каждой паре)
```

## Стек

| Компонент | Технология |
|---|---|
| Runtime | Python 3.14 |
| Package manager | uv |
| Linter / Formatter | ruff |
| Web framework | FastAPI |
| Search engine | OpenSearch 2.x |
| Векторные эмбеддинги | sentence-transformers (all-MiniLM-L6-v2, 384d) |
| Хранение результатов | MongoDB (Motor async driver) |
| Тесты | pytest + pytest-asyncio |
| Контейнеризация | Docker + docker-compose |

## Архитектура

Проект построен на принципах Clean Architecture внутри Modular Monolith:

```
Presentation → Application → Domain (optional) ← Infrastructure
```

Три модуля:

| Модуль | Роль |
|---|---|
| `search` | Алгоритмы поиска, индексирование документов, метрики eval |
| `experiments` | Библиотека алгоритмов, шаблоны запросов, бенчмарк-раны |
| `agents` | (в разработке) LLM-агенты для обогащения запросов |

Модули общаются только через публичный `api.py`. Подробнее — в [`docs/decisions/`](docs/decisions/README.md).

## Структура директорий

```
new_search/
├── src/
│   ├── main.py                    # Точка входа FastAPI
│   ├── shared/                    # Общий код (embedding, opensearch, mongodb)
│   └── modules/
│       ├── search/                # Алгоритмы, eval-метрики, индексирование
│       │   ├── api.py
│       │   ├── application/       # search_service, eval_service, indexing_service
│       │   ├── infrastructure/    # OpenSearch репозиторий
│       │   └── presentation/      # Роутеры: /search, /eval, /documents
│       ├── experiments/           # Ядро платформы тестирования
│       │   ├── api.py
│       │   ├── domain/            # Algorithm, QueryTemplate, BenchmarkRun
│       │   ├── application/       # experiments_service (N×M benchmark runner)
│       │   ├── infrastructure/    # MongoDB репозиторий
│       │   └── presentation/      # /experiments/algorithms, /templates, /benchmark
│       └── agents/                # (заглушка) LLM-агенты
├── tests/
│   ├── unit/                      # Юнит-тесты, без I/O
│   ├── integration/               # С реальным OpenSearch
│   └── e2e/                       # End-to-end сценарии
├── scripts/
│   ├── seed.py                    # Заполнение индексов тестовыми данными
│   └── semantic_search_demo.py    # Демонстрация семантического поиска
├── static/
│   └── index.html                 # Web UI для поиска и бенчмарков
└── docs/
    ├── decisions/                 # Architecture Decision Records (ADR)
    └── developer-setup.md
```

## Быстрый старт

### Требования

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Docker + docker-compose

### Установка

```powershell
# Установить зависимости
uv sync --all-extras

# Запустить инфраструктуру (OpenSearch + MongoDB)
docker-compose up -d opensearch mongodb

# Заполнить индекс тестовыми данными
uv run python scripts/seed.py

# Запустить приложение
make dev
```

После запуска:
- Web UI: `http://localhost:8000`
- Swagger API: `http://localhost:8000/docs`
- OpenSearch Dashboards: `http://localhost:5601`

### Основные команды

```powershell
make dev        # Запуск с hot-reload
make test       # Запуск тестов
make lint       # Проверка кода (ruff)
make format     # Форматирование кода (ruff)
make docker-up  # Поднять всю инфраструктуру
```

## Принципы разработки

- **Async-first** — все операции с I/O асинхронны
- **Строгая типизация** — `Any` запрещён, все типы явны
- **Нет магических строк** — константы и перечисления обязательны
- **Логирование** — структурированный JSON через `structlog`, всегда включать `request_id`
- **Тесты** — юнит-тесты мокают весь I/O; интеграционные — с реальным OpenSearch

## Архитектурные решения

Все архитектурные решения задокументированы в [`docs/decisions/`](docs/decisions/README.md).

## Настройка окружения разработчика

Инструкция по настройке и персонализации поведения агентов: [`docs/developer-setup.md`](docs/developer-setup.md).
