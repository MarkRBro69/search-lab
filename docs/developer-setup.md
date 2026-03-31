# Developer Setup

**Search Lab** is a platform for testing search algorithms on OpenSearch.
This guide walks you through running the project locally and customising LLM-agent behaviour.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — install globally
- Docker Desktop (or Docker Engine + docker-compose)
- Cursor IDE

## Installation

```powershell
# 1. Clone the repository
git clone <repo-url>
cd new_search

# 2. Install dependencies (uv creates .venv automatically)
uv sync --all-extras

# 3. Install pre-commit hooks
uv run pre-commit install

# 4. Copy the environment file
Copy-Item .env.example .env
# Open .env and fill in the required values
```

## Starting the Infrastructure

```powershell
# Minimum required (OpenSearch + MongoDB are both needed)
docker-compose up -d opensearch mongodb

# Full stack (+ Dashboards + app in a container)
docker-compose up -d

# Check status
docker-compose ps
```

## Running the Application

```powershell
uv run uvicorn src.main:app --reload
```

The app will be available at `http://localhost:8000`.
Swagger UI: `http://localhost:8000/docs`.

---

## Personal Agent Profile

Each developer can customise LLM-agent behaviour: communication language, terminal syntax, confirmation level.

### How to create a profile

**Step 1.** Copy the template:

```powershell
Copy-Item .cursor\templates\developer-profile.mdc .cursor\rules\local\my-profile.mdc
```

**Step 2.** Open `.cursor/rules/local/my-profile.mdc` and fill in the fields:

```markdown
---
description: Personal developer profile
alwaysApply: true
---

# Developer Profile

- OS: windows
- Shell: powershell
- Communication language: en
- Terminal command style: always use PowerShell syntax in suggestions
- Confirmation: yes
- Verbosity: concise
```

**Step 3.** Save the file. Cursor will pick it up automatically in the next session.

> This file is gitignored and will not be committed to the repository.

### Field reference

| Field | Values | Effect |
|---|---|---|
| `OS` | `windows`, `macos`, `linux` | Agent is aware of platform specifics |
| `Shell` | `powershell`, `bash`, `zsh` | All terminal commands use the right syntax |
| `Communication language` | `ru`, `en` | Language for responses, comments, commit messages |
| `Confirmation` | `yes`, `no` | Whether to ask for confirmation before multi-step plans |
| `Verbosity` | `concise`, `detailed` | Short or detailed explanations |

### Examples

**Windows / PowerShell / English:**
```markdown
- OS: windows
- Shell: powershell
- Communication language: en
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

## Agent Rules Structure

All rules in `.cursor/rules/` are applied automatically by agents:

| File | When applied |
|---|---|
| `project-overview.mdc` | Always |
| `architecture.mdc` | Always |
| `agent-workflow.mdc` | Always |
| `tooling.mdc` | Always |
| `git-conventions.mdc` | Always |
| `logging.mdc` | Always |
| `fastapi-conventions.mdc` | When working with `.py` files |
| `testing.mdc` | When working with `tests/` |
| `opensearch-patterns.mdc` | When working with `src/modules/search/infrastructure/` |
| `llm-agent-integration.mdc` | When working with `src/modules/agents/` |
| `local/my-profile.mdc` | Always (personal, gitignored) |
