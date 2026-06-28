# MCP Tool Execution

The healthcare backend can execute tools in two modes:

- `TOOL_EXECUTION_MODE=local`: current behavior. Tool call execution stays in the backend.
- `TOOL_EXECUTION_MODE=mcp`: supervisor routing, specialist selection, and tool selection stay in the backend, but the selected tool call is sent to the MCP server.

## Backend Flow

1. `KnowledgeAgent` builds the same `AgentTool` names and descriptions.
2. The supervisor/specialist graph chooses a tool as before.
3. `ToolExecutionRouter` checks `TOOL_EXECUTION_MODE`.
4. In local mode, it calls the local function.
5. In MCP mode, it calls the selected MCP tool name directly on the configured MCP server with:
   - `project_id`
   - query
   - user roles/departments
   - tool-specific metadata such as table assets

## MCP Server

The MCP server repo is `../MCP-Tools`. It is an external service, not a service in this project's Compose file. It exposes a FastMCP SSE endpoint and registers each healthcare project tool with `@mcp.tool()`.

The first registered project is:

```text
dstrmaysam-healthcare-knowledge-multi-agent
```

Current healthcare tool execution includes:

- `postgres_deterministic_lookup`
- `calendar_rota_lookup`
- `formulary_table_lookup`
- `document_search` / `rag_search`
- `policy_search`
- `catalogue_search` / `document_catalog`
- `safety_guard`

## Local Compose

The main compose file does not include an MCP container. Start the external MCP service from `../MCP-Tools`, then point the backend at that service.

Use:

```env
TOOL_EXECUTION_MODE=mcp
MCP_SERVER_URL=http://host.docker.internal:9000/sse
MCP_PROJECT_ID=dstrmaysam-healthcare-knowledge-multi-agent
```

## AWS Later

Host the MCP server as a separate ECS service. Give it its own task role and configure access to:

- RDS Postgres for operational table lookup
- S3/OpenSearch if document retrieval is moved fully into MCP
- Secrets Manager for project-specific credentials

The backend service only needs network access to the MCP service endpoint and does not need to know how each tool is implemented.
