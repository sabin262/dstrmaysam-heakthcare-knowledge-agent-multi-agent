# MCP Tool Execution

The healthcare backend can execute tools in two modes:

- `TOOL_EXECUTION_MODE=local`: current behavior. Tool call execution stays in the backend.
- `TOOL_EXECUTION_MODE=mcp`: supervisor routing, specialist selection, and tool selection stay in the backend, but the selected tool call is sent to the MCP server.

## Backend Flow

1. `KnowledgeAgent` builds the same `AgentTool` names and descriptions.
2. The supervisor/specialist graph chooses a tool as before.
3. `ToolExecutionRouter` checks the resolved tool execution mode.
4. In local mode, it calls the local function.
5. In MCP mode, it calls the agent-selected MCP tool directly with:
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
MCP_TOOL_TIMEOUT_SECONDS=30
MCP_TOOL_FALLBACK_TO_LOCAL=false
```

## AWS Deployment

The healthcare foundation stack owns this project's MCP runtime infrastructure inside the healthcare dev VPC:

- ECR repository: `dstrmaysam-healthcare-knowledge-multi-agent-dev-mcp`
- ECS/Fargate service: `dstrmaysam-healthcare-knowledge-multi-agent-dev-mcp`
- Cloud Map URL: `http://mcp-tools.dstrmaysam-hkm-dev.local:9000/sse`
- Public dev ALB URL from the `McpPublicUrl` stack output
- Security group allowing inbound `9000` from the backend/app task security group and the dev ALB security group
- RDS ingress from the MCP security group on `5432`
- MCP task role, log group, and OpenSearch Serverless data access policy principal

The MCP repo remains separate. Its own CodePipeline builds the MCP image, pushes `mcp-<commit>` and `mcp-latest`, then updates only the MCP ECS service created by the healthcare stack.

Use the Cloud Map URL for backend-to-MCP calls inside the same VPC. Use the `McpPublicUrl` output for dev calls from outside the VPC. Public access is controlled by the stack `PublicIngressCidr` parameter.

In AWS mode, store `tool_execution_mode`, `mcp_server_url`, `mcp_project_id`, `mcp_tool_timeout_seconds`, and `mcp_tool_fallback_to_local` in the backend app secret in Secrets Manager instead of ECS task environment variables. Use:

```json
{
  "tool_execution_mode": "mcp",
  "mcp_server_url": "http://mcp-tools.dstrmaysam-hkm-dev.local:9000/sse",
  "mcp_project_id": "dstrmaysam-healthcare-knowledge-multi-agent",
  "mcp_tool_timeout_seconds": 30,
  "mcp_tool_fallback_to_local": false
}
```

Give the MCP service its own task role and configure access to:

- RDS Postgres for operational table lookup
- S3/OpenSearch if document retrieval is moved fully into MCP
- Secrets Manager for project-specific credentials

The backend service only needs network access to the MCP service endpoint and does not need to know how each tool is implemented.
