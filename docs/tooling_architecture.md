# Tooling Architecture

The multi-agent graph currently executes tools in-process, but tool construction is isolated under `backend/app/tooling/` so execution can move to an MCP service without changing the supervisor graph contract.

## Current Layout

- `backend/app/tooling/base.py` defines `AgentTool` and the core local tools: RAG search, document catalog, and table lookup.
- `backend/app/tooling/healthcare.py` defines local healthcare tools: document search, policy search, catalogue search, rota lookup, formulary lookup, deterministic Postgres lookup, and safety guard.
- `backend/app/tooling/registry.py` centralizes local registry construction.
- `backend/app/tools.py` and `backend/app/healthcare_tools.py` are compatibility shims for older imports.

## Boundary For MCP Migration

The graph and specialist agents should continue to work with `AgentTool` objects:

- `name`: stable backend tool identifier.
- `description`: routing hint exposed to the LLM.
- `run(query)`: execution function returning a string payload.

When tools move out of process, keep these names and descriptions stable. Replace the `run(query)` implementation with a client call that packages the query, user context, CSV asset metadata, and request-scoped settings for the MCP server.

## Contract To Preserve

- Public `/chat` request and response schemas do not change.
- `tools_used` remains a list of backend tool names.
- `agent_flow`, `agents_used`, `supervisor_decisions`, `agent_latencies_ms`, and `agent_errors` continue to be saved.
- The supervisor still selects specialist agents. Specialists still select tools. Only the execution backend changes.
