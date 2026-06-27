# Moving Tools To An MCP Server

The application can now run tools locally or forward tool execution to an external FastMCP service while preserving the multi-agent graph.

## Runtime Modes

- `TOOL_EXECUTION_BACKEND=local`: use in-process tool definitions under `backend/app/tooling/`.
- `TOOL_EXECUTION_BACKEND=mcp`: expose the same tool names to the supervisor graph, but call the external MCP server for execution.

Required MCP settings:

```env
TOOL_EXECUTION_BACKEND=mcp
MCP_TOOL_SERVER_URL=https://<tool-service-host>/mcp
MCP_TOOL_TIMEOUT_SECONDS=20
```

## Tool Contract

Each MCP tool should keep the same name as the local tool:

- `rag_search`
- `document_catalog`
- `table_lookup`
- `document_search`
- `policy_search`
- `catalogue_search`
- `calendar_rota_lookup`
- `formulary_table_lookup`
- `postgres_deterministic_lookup`
- `safety_guard`

The backend sends a single payload:

```json
{
  "tool": "postgres_deterministic_lookup",
  "query": "who is on call",
  "user": {
    "user_id": "admin",
    "roles": ["admin", "doctor"],
    "departments": ["operations"],
    "password_change_required": false
  },
  "app_context": {
    "settings": {
      "app_env": "dev",
      "tool_execution_backend": "mcp"
    }
  }
}
```

The MCP server should return a string. JSON strings are preferred for structured lookup tools because the synthesis layer already understands deterministic lookup payloads.

## Migration Steps

1. Copy the logic from `backend/app/tooling/base.py` and `backend/app/tooling/healthcare.py` into a separate MCP service.
2. Give each MCP tool the same public name and a compatible input schema with `query`, `user`, and `app_context`.
3. Ensure the MCP service has access to its required dependencies: document store, retrieval index, Postgres lookup database, safety policy code, and secrets.
4. Deploy the MCP service behind an internal HTTPS endpoint.
5. Configure the backend with `TOOL_EXECUTION_BACKEND=mcp` and `MCP_TOOL_SERVER_URL`.
6. Run chat regression tests and verify `tools_used`, `agent_flow`, and dashboard metadata still show the same tool and agent names.

## What Does Not Change

- `/chat` request and response schema.
- Supervisor-led multi-agent graph.
- Tool names in `tools_used`.
- Dashboard metadata fields.
- RAGAS and Langfuse tracing behavior.
