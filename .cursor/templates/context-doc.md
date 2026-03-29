# Context Document — Stage 1 Output

> This template is filled by the **Context Gatherer** agent (Stage 1).
> The completed document is passed as input to the **Architect** agent (Stage 2).
> Keep it factual — no solutions or proposals.

---

## 1. Engineer's Request

> Paste the original request verbatim. Do not paraphrase.

```
[ORIGINAL REQUEST HERE]
```

---

## 2. Clarifications

> Questions asked and answers received from the engineer.
> If no clarification was needed, write "None required."

| Question | Answer |
|---|---|
| | |

---

## 3. Affected Modules

> List modules from `src/modules/` that will need changes.

- [ ] `search` — reason: 
- [ ] `agents` — reason: 
- [ ] `shared` — reason: 

---

## 4. Affected Files

> Specific files identified by scanning the codebase.

```
src/modules/search/
  application/        # [describe what needs changing]
  infrastructure/     # [describe what needs changing]
```

---

## 5. External Dependencies

> OpenSearch indices, LLM tools, third-party APIs that will be touched.

| Type | Name / Identifier | Notes |
|---|---|---|
| OpenSearch index | | |
| LLM tool | | |
| External API | | |

---

## 6. Constraints and Risks

> Technical constraints, performance requirements, backwards-compatibility concerns.

- 
- 

---

## 7. Open Questions

> Unresolved questions that the Architect should be aware of.
> These may require assumptions or flags in the task spec.

- [ ] 
- [ ] 
