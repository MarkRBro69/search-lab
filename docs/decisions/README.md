# Architecture Decision Records (ADR)

This folder documents significant architectural decisions made in the project.

## What Is an ADR?

An ADR captures **why** a decision was made — not just what was decided.
It records the context, the alternatives considered, and the consequences.

Future developers (and LLM agents) can read ADRs to understand why the codebase
is structured the way it is, and avoid relitigating settled decisions.

## Format

Each ADR is a Markdown file named `ADR-{number}-{short-title}.md`.

```markdown
# ADR-XXXX: Title

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXXX]

## Context
What problem or situation prompted this decision?

## Decision
What was decided?

## Alternatives Considered
What other options were evaluated?

## Consequences
What are the trade-offs? What becomes easier or harder?
```

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](ADR-0001-architecture.md) | Clean Architecture + Modular Monolith | Accepted |
| [ADR-0002](ADR-0002-evaluation-framework.md) | Search Evaluation Framework | Accepted |

## When to Write an ADR

Write an ADR when:
- Choosing between two or more valid architectural approaches
- Making a decision that would be hard or expensive to reverse
- A decision might surprise a new team member or agent

Do NOT write an ADR for:
- Implementation details that can change freely
- Decisions that follow obviously from existing ADRs
