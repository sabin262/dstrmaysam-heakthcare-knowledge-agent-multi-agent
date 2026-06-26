# Multi-Agent Chat Regression Context

## Purpose

This file is the context document to use when finishing the migration from the original single-agent/fast-path chat flow to the new multi-agent supervisor architecture.

The current regression risk is that the old deterministic preflight path looked like a separate execution mode, but it also carried a lot of hidden product behavior:

- deciding when structured Postgres/CSV lookup was needed,
- rewriting short medicine/entity queries,
- formatting deterministic-only answers consistently,
- preventing stale chat history or RAG chunks from overriding live structured data,
- preserving tool flow/dashboard metadata,
- avoiding unnecessary RAG when exact table data was enough.

If `Deterministic + Agent` mode is removed, those behaviors must move into the supervisor and synthesis flow. They should not disappear.

## Current Desired User Experience

The chat should behave as a single multi-agent experience:

- no visible execution-mode selector,
- no `Deterministic + Agent` vs `Agent only` choice in the UI,
- backend may still accept legacy `execution_mode` for compatibility, but it should normalize to one internal mode: `supervisor`,
- the LLM supervisor chooses specialist agents/tools,
- deterministic lookup remains available as a specialist tool,
- deterministic structured answers remain as accurate and consistent as the old preflight answers.

## Important Baseline Behaviors To Preserve

### Deterministic Lookup Must Still Handle Exact Structured Questions

The `postgres_deterministic_lookup` tool must remain the authoritative path for:

- patients, patient location, MRN/NHS identifiers,
- appointments, clinics, wards,
- doctors, nurses, staff rota, on-call availability,
- departments and contacts,
- formulary and medicine facts,
- uploaded CSV lookup rows,
- inventory/equipment/asset counts,
- row-value questions such as `How many ventilators do we have?`.

The multi-agent supervisor should route these to `DeterministicLookupAgent`.

### Do Not Treat Removing Preflight As Removing Deterministic Logic

The old `_call_deterministic_entity_preflight(...)` should not remain as a direct-answer bypass in the final multi-agent design, but its behavior must be preserved elsewhere.

Move these behaviors into the supervisor/specialist/synthesis path:

- short entity intent detection,
- list intent detection,
- count/aggregate intent detection,
- row-value search intent detection,
- medicine fallback query rewrite,
- deterministic-only answer formatting,
- exact count/details formatting,
- direct use of Postgres rows instead of RAG snippets.

### Preserve Short Entity Query Rewrite

Old behavior:

```text
info on Morphine
```

If the direct lookup failed, the system retried:

```text
medicine info on Morphine
```

This matters for formulary/medicine questions. In multi-agent flow:

- the supervisor should choose `postgres_deterministic_lookup`,
- the deterministic specialist should perform the same fallback rewrite internally,
- the synthesis step should use the effective query and exact rows,
- metadata should record the effective query.

### Preserve Deterministic-Only Formatting

When only `postgres_deterministic_lookup` is used, do not send raw JSON-like row summaries to the final answer.

Use the old deterministic formatter behavior:

- single entity: title + bullet details,
- list query: numbered list of the requested entity names only,
- count query: total first, then relevant details,
- equipment count query: total first, then location and status bullets,
- missing rows: state that no matching structured row was found.

Examples to preserve:

```text
information on morphine
```

Expected shape:

```text
Morphine details are as follows:

- Category: ...
- Restricted: ...
- Approval required: ...
- Maximum adult dose: ...
- Monitoring required: ...
- Access level: ...
```

```text
list all medicine in formulary
```

Expected shape:

```text
Medicines returned by deterministic lookup:

1. Morphine
2. Oxycodone
3. Fentanyl patch
...
```

Do not return generic `Record - Category: ...` lines for list-name queries.

```text
how many ventilators do we have
```

Expected shape:

```text
Total: 3 matching row(s) in equipment_assets.csv.

Details:
- Ventilator; Location: ICU Ward; Status: Available
- Ventilator; Location: Respiratory Ward; Status: Fault logged
- Ventilator; Location: Mental Health Ward; Status: Available
```

Do not mix unrelated equipment types such as dialysis machines into ECG machine answers.

### Preserve RAG And Policy Behavior

Policy/document questions should still go through retrieval specialists:

- `policy_search` for policy/SOP/pathway/guideline/compliance questions,
- `rag_search` for general document Q&A,
- `document_catalog`/catalog helper for document inventory and catalog-guided retrieval.

Catalog-guided RAG should still:

- load candidate documents from the manifest,
- filter by role access,
- narrow OpenSearch/Chroma retrieval using candidate document keys,
- record `document_catalog` in `tool_flow` as a helper when used,
- keep `tools_used` limited to tools selected by the agent.

### Preserve Multipart Behavior

Multipart questions must call every relevant specialist before synthesis.

Example:

```text
What is the incident reporting policy and who is on call today?
```

Expected flow:

```text
SupervisorAgent
  -> PolicyAgent / policy_search
  -> DeterministicLookupAgent / postgres_deterministic_lookup
  -> SynthesisAgent
```

The final answer should combine evidence without letting one tool overwrite the other.

### Preserve Observability Metadata

Every chat must continue to save:

- `tools_used`,
- `tool_flow`,
- `agent_flow`,
- `agents_used`,
- `supervisor_decisions`,
- `agent_latencies_ms`,
- `agent_errors`,
- `catalog_guidance`,
- `source_count`,
- `source_document_keys`,
- `chat_execution_mode`,
- `chat_execution_mode_label`,
- `performance`,
- `latency_breakdown`,
- Langfuse trace ID,
- RAGAS status/scores when available.

For the final single-mode architecture:

```json
{
  "chat_execution_mode": "supervisor",
  "chat_execution_mode_label": "Supervisor"
}
```

Historical dashboard rows may still contain old values and should render safely.

## How To Remove `Deterministic + Agent` Mode Safely

### Backend API

Keep `ChatRequest.execution_mode` optional for backward compatibility:

```python
execution_mode: str | None = None
```

Do not reject old clients that send:

- `agent_only`,
- `deterministic_agent`,
- `deterministic_only`,
- unknown values.

Normalize all values internally to:

```text
supervisor
```

The `/chat` route should ignore incoming `execution_mode` and call:

```python
agent.answer(..., execution_mode=None)
```

### Frontend

Remove:

- mode dropdown,
- mode change notices,
- `pending_chat_execution_mode`,
- sending `execution_mode` in `/chat` payloads.

Keep:

- fixed-bottom chat input,
- transient progress updates,
- chat window persistence while answer is processing,
- new chat and history controls on the chat page only.

### Agent Internals

Remove direct preflight bypass from `_generate_agent_response(...)`.

Do not do this:

```text
if deterministic-looking query:
    answer directly before supervisor graph
```

Instead:

1. Build the normal supervisor prompt.
2. Let the supervisor LLM choose tools.
3. Add deterministic routing guardrails inside the supervisor graph:
   - if the query matches deterministic/list/count/row-value intent and the supervisor tries to answer directly, force a deterministic lookup route;
   - if the supervisor chooses only RAG for clear structured lookup intent, add deterministic lookup before synthesis;
   - if the query is multipart, keep all tool calls.
4. Run deterministic lookup as a specialist node.
5. Use deterministic-only formatter in synthesis when only `postgres_deterministic_lookup` was used.

This keeps the architecture multi-agent without losing the accuracy protection that preflight used to provide.

## Recommended Multi-Agent Flow

### SupervisorAgent

Responsibilities:

- choose specialist route(s),
- avoid direct memory answers for operational facts,
- route exact structured questions to `DeterministicLookupAgent`,
- route policy/document questions to `PolicyAgent` or `RAGAgent`,
- route catalog/inventory questions to `CatalogAgent`,
- route safety/escalation requests to `SafetyAgent`,
- emit complete `supervisor_decisions`.

Recommended routing prompt requirements:

```text
- For patients, appointments, wards, rota, contacts, departments, formulary, medicines, CSV rows, equipment, assets, devices, counts, totals, and list queries, call postgres_deterministic_lookup.
- For policies, SOPs, pathways, guidelines, compliance, privacy, confidentiality, and governance, call policy_search.
- For general document Q&A, call rag_search.
- For available documents, document inventory, or metadata, call catalogue_search.
- For urgent clinical risk, escalation, PHI, or unsafe requests, call safety_guard.
- If the query has multiple parts, call every relevant specialist before synthesis.
- Do not answer directly unless the question is a greeting or needs no knowledge source.
```

### DeterministicLookupAgent

Responsibilities:

- call `postgres_deterministic_lookup`,
- pass the original user query,
- perform medicine fallback rewrite when needed,
- preserve effective query in metadata,
- return structured JSON/tool context,
- expose rows and aggregate results to synthesis,
- avoid LLM interpretation of exact values.

### RAGAgent / PolicyAgent

Responsibilities:

- call retrieval-backed tools,
- keep catalog-guided narrowing,
- return sources with non-empty snippets,
- preserve citations and source metadata,
- record catalog helper steps in `tool_flow`.

### SynthesisAgent

Responsibilities:

- produce the final answer from specialist evidence only,
- preserve exact deterministic values,
- use old deterministic formatter for deterministic-only answers,
- combine multiple tool results for multipart queries,
- cite document sources when retrieval sources exist,
- say what is missing when evidence is insufficient.

## Regression Traps

### Trap 1: Supervisor Direct Answer For Structured Queries

Bad:

```text
User: how many ventilators do we have
Assistant: The documents do not specify...
```

Fix:

- route to `postgres_deterministic_lookup`,
- use row-value search over uploaded CSV rows,
- count matching Postgres rows.

### Trap 2: RAG Overrides Deterministic Lookup

Bad:

```text
User: info on morphine
Assistant: No policy document mentions Morphine...
```

Fix:

- deterministic lookup first for short medicine/entity facts,
- RAG only if the question asks for policy/document interpretation.

### Trap 3: List Queries Return Full Row Summaries

Bad:

```text
Record - Category: Anticoagulant; Restricted: No...
```

Fix:

- identify requested name field,
- return only entity names for list queries,
- use unique values when the query asks for types.

### Trap 4: Row-Value Search Uses Loose OR Matching

Bad:

```text
how many ecg machines do we have
```

returns ECG machines and dialysis machines.

Fix:

- exact phrase/value matching should outrank generic asset/table matches,
- require equipment type match for equipment-type count questions,
- do not include rows that only match generic table/category terms.

### Trap 5: Dashboard Loses Decision Tree

Bad:

```text
No supervisor decision tree captured for this query.
```

Fix:

- every supervisor route appends a `SupervisorAgent` step,
- every specialist appends its agent/tool step,
- synthesis appends a final `SynthesisAgent` step.

## Minimum Acceptance Tests

Backend agent tests:

- `info on Morphine` routes to deterministic lookup and returns bullet details.
- `info on diazepam` and `details on paracetamol` use the same response structure as morphine.
- `list all medicine in formulary` returns only medicine names.
- `list all equipment we have` returns unique equipment types from `equipment_assets.csv`.
- `how many ventilators do we have` returns total, location, and status.
- `how many ecg machines do we have` excludes dialysis machines.
- policy question routes to `policy_search` and returns sources/snippets.
- multipart policy plus rota question calls both policy and deterministic specialists.
- old `execution_mode=agent_only` and `execution_mode=deterministic_agent` are accepted but normalized to `supervisor`.
- dashboard metadata contains `agent_flow`, `tool_flow`, and `supervisor_decisions`.

Frontend tests/manual checks:

- no chat mode selector is visible,
- chat payload does not include `execution_mode`,
- chat still shows user question immediately while processing,
- chat window does not disappear during processing,
- dashboard renders historical old-mode rows and new supervisor-mode rows.

## Files To Review During Implementation

Primary backend files:

- `backend/app/agent.py`
- `backend/app/deterministic_lookup.py`
- `backend/app/healthcare_tools.py`
- `backend/app/models.py`
- `backend/app/main.py`

Primary frontend file:

- `frontend/streamlit_app.py`

Primary tests:

- `tests/test_agent_contract.py`
- `tests/test_deterministic_lookup.py`
- `tests/test_models.py`
- `tests/test_user_management.py`

## Implementation Guidance

Do the migration in this order:

1. Lock `execution_mode` normalization to `supervisor`.
2. Remove frontend mode selector and payload field.
3. Keep deterministic lookup as a specialist tool.
4. Move preflight behavior into deterministic specialist and synthesis formatter.
5. Add deterministic routing guard inside supervisor flow.
6. Preserve `agent_flow`, `tool_flow`, and dashboard metadata.
7. Run focused regression tests for deterministic rows and RAG/policy.
8. Only then remove dead preflight code.

Do not delete deterministic helpers until all acceptance tests above pass.

## Short Answer To The Design Question

If you remove `Deterministic + Agent` mode, the functionality is preserved only if deterministic lookup stops being a mode and becomes a first-class specialist capability inside the supervisor graph.

The system should no longer answer before the graph through deterministic preflight, but the supervisor must still be forced or strongly guided to call deterministic lookup for exact structured facts. The deterministic specialist and synthesis agent must preserve the old formatter and row-value lookup behavior.
