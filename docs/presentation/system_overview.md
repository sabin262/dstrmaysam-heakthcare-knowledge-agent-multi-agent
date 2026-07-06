# Healthcare Knowledge Multi-Agent System Overview

This document summarises the current system from the codebase. It intentionally does not rely on older documents in the docs folder.

## Purpose

The system provides a governed hospital knowledge assistant. Staff can ask operational, policy, document, contact, patient, equipment, formulary, and safety-related questions from one chat interface. Admin users can manage documents, CRM data, settings, dashboards, and system-level evaluations.

## Main User-Facing Capabilities

- Chat assistant with multi-agent routing, source-aware answers, and query trace metadata.
- Hospital CRM for patients, doctors, departments, schedules, appointments, finance, and other operational tables.
- Document management with upload, metadata editing, ingestion, chunking, indexing, and catalog visibility.
- Admin dashboard for per-query details, agents used, tool execution location, latency, cost, RAGAS details, and routing traces.
- Evaluations page for golden dataset and stress-test runs against the full chat system.
- Settings page for tool execution mode and MCP server selection.
- Twilio WhatsApp webhook support for chat access outside the main UI.

## Backend Components

- FastAPI app: `backend/app/api/app.py`
  - Auth and user management.
  - Chat endpoint: `POST /chat`.
  - Document upload and ingestion endpoints.
  - CRM CRUD endpoints.
  - Dashboard and evaluation endpoints.
  - Twilio webhook endpoint: `POST /twilio/whatsapp/webhook`.
- Multi-agent orchestration: `backend/app/agents/knowledge_agent.py`
  - Uses LangGraph to run the in-process multi-agent workflow.
  - Public API shape remains stable while internal routing is handled by agents.
- Tool execution: `backend/app/tool_execution.py`
  - Routes tool calls either to local tool execution or to an MCP server.
  - Records actual execution location and fallback status for dashboard visibility.
- Shared healthcare tool package:
  - `backend/packages/healthcare_tools_core/src/healthcare_tools_core`
  - Shared by the healthcare backend and MCP server so table lookup and retrieval logic stay aligned.

## Agents

- `SupervisorAgent`: selects the next specialist agent and arbitrates reports.
- `DeterministicLookupAgent`: handles exact Postgres-backed operational facts such as patients, appointments, rota, departments, wards, equipment, contacts, formulary, finance, counts, lists, and row-level queries.
- `PolicyAgent`: handles policies, SOPs, pathways, compliance, governance, retention, research, and other policy evidence questions.
- `RAGAgent`: handles broader document-content retrieval that is not specifically a policy inventory or exact database lookup.
- `CatalogAgent`: handles document inventory and metadata questions.
- `SafetyAgent`: reviews urgent, risky, PHI-sensitive, escalation, or clinical-safety-sensitive responses.
- `SynthesisAgent`: produces the final user-facing answer from specialist reports.

## Tool Model

The current architecture keeps reasoning in the healthcare backend. Specialists choose tools, and the tool execution router decides whether the selected tool runs locally or through MCP.

Healthcare tools include:

- `postgres_deterministic_lookup`
- `document_search`
- `rag_search`
- `policy_search`
- `catalogue_search`
- `document_catalog`
- `safety_guard`
- compatibility wrappers such as `calendar_rota_lookup`, `formulary_table_lookup`, and `table_lookup`

In MCP mode, the backend sends the selected tool name and payload to the MCP server. The MCP server executes the tool and returns the result. The backend still owns supervisor routing, specialist selection, synthesis, safety orchestration, and public response formatting.

## Data And Retrieval

- Postgres stores operational CRM data, lookup tables, chat history, evaluation history, and seeded hospital data.
- S3 stores uploaded documents and metadata/manifest assets in AWS mode.
- OpenSearch Serverless stores indexed document chunks in AWS mode.
- Local mode uses local equivalents where configured, including local Postgres and local vector storage.
- Supported CSV uploads update known Postgres tables rather than creating arbitrary CSV row blobs.
- Document ingestion preserves metadata, deletes old chunks for changed documents, then writes fresh chunks.

## AWS Deployment

The healthcare stack is defined in `infra/aws-foundation.yml`. It creates or configures:

- VPC, public/private subnets, route tables, Internet Gateway, and S3 gateway endpoint.
- S3 bucket for documents and manifest data.
- Secrets Manager secrets for application, Azure OpenAI, Langfuse, and MCP settings.
- RDS Postgres instance and security groups.
- OpenSearch Serverless collection and access policies.
- ECR repositories for app and MCP images.
- ECS cluster, task definitions, services, task roles, execution roles, and log groups.
- Public ALB with frontend, backend, and optional MCP listener rules.
- CodePipeline and CodeBuild resources for build/deploy automation.
- Optional attachment to the shared MCP Transit Gateway so the shared MCP stack can reach the healthcare RDS instance.

## Shared MCP Stack

The MCP server lives in a separate repository at `C:\Users\Sabin\Documents\ITC Projects\MCP-Tools`.

The shared stack template at `MCP-Tools\infra\shared-mcp-stack.yml` creates:

- Separate shared MCP VPC.
- Transit Gateway and route tables for project VPC connectivity.
- Internal ALB for MCP access from connected project networks.
- ECS/Fargate MCP service.
- ECR repository.
- CodePipeline and CodeBuild for MCP repo deployment.
- Shared secret registry that points to project-level MCP secrets.

## Request Flow

1. The user submits a chat query through Streamlit, WhatsApp, or an API caller.
2. FastAPI authenticates the user and passes user role/context to the chat agent.
3. The supervisor decides which specialist should handle the question.
4. The specialist chooses its allowed tool and validates returned evidence.
5. The tool runs locally or through MCP, depending on current settings.
6. The supervisor may request another specialist, route to safety review, or move to synthesis.
7. The synthesis agent creates the final answer from specialist evidence.
8. Query metadata is saved for dashboard and evaluation review.

## Governance And Assurance

- Role-based responses for patient detail queries.
- Safety review for urgent, risky, PHI, escalation, and clinical-safety cases.
- Source and tool metadata stored per query.
- Dashboard visibility for actual local/MCP execution and fallback.
- Golden dataset and stress-test evaluations for routing, tools, required facts, forbidden facts, sources, safety, and latency.
- Optional RAGAS scoring remains informational; system pass/fail comes from contract-style evaluations.

## Current Strengths

- Clear separation between agent reasoning and tool execution.
- Shared tool package reduces local/MCP drift.
- Rich operational data path through Postgres rather than generic CSV row lookup.
- Admin controls and evaluations make regressions visible.
- AWS architecture supports local mode, healthcare-owned MCP, and shared MCP patterns.

## Current Challenges

- Routing quality depends on metadata completeness and guardrails.
- RAG and policy retrieval need ongoing tuning against real failure cases.
- MCP networking and secrets must stay aligned across stacks and VPCs.
- More autonomous specialist behavior can add latency and LLM cost.
- Production HTTPS, monitoring, alerting, and stronger network hardening are still next-phase work.
