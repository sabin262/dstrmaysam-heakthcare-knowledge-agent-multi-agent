# AWS Multi-Agent Architecture

Project: `dstrmaysam-healthcare-knowledge-multi-agent`

This document describes the high-level and low-level design for the multi-agent healthcare knowledge system deployed on AWS.

## HLD 1: Stakeholder View

```mermaid
flowchart LR
    User["Clinician or admin user"] --> Frontend["Healthcare knowledge chat UI"]
    Frontend --> Backend["Multi-agent knowledge service"]
    Backend --> Knowledge["Hospital knowledge sources"]
    Backend --> LLM["Azure OpenAI"]
    Backend --> Audit["Tracing and evaluation"]

    Knowledge --> Documents["Policies, SOPs, guidance, and uploaded files"]
    Knowledge --> Structured["CSV-uploaded operational data in Postgres"]
```

The stakeholder view has four main ideas:

- Users ask questions in one chat interface.
- The backend supervisor decides which specialist agent should handle each part of the question.
- The system uses hospital documents, structured operational rows, and Azure OpenAI to answer.
- Tracing, saved chat history, and evaluation data support audit and improvement.

## HLD 2: Technical AWS View

```mermaid
flowchart TB
    GitHub["GitHub repository"] --> Pipeline["CodePipeline"]
    Pipeline --> Build["CodeBuild"]
    Build --> ECR["ECR backend and frontend repositories"]
    Pipeline --> Deploy["CodeDeploy blue/green"]
    Deploy --> ECS["ECS Fargate services"]

    ALB["Application Load Balancer"] --> Frontend["Streamlit frontend task"]
    ALB --> Backend["FastAPI backend task"]
    Frontend --> Backend

    Backend --> RDS["RDS PostgreSQL"]
    Backend --> S3["S3 document bucket"]
    Backend --> OpenSearch["OpenSearch Serverless"]
    Backend --> Secrets["Secrets Manager"]
    Backend --> Azure["Azure OpenAI"]
    Backend --> Langfuse["Langfuse"]

    ECS --> Logs["CloudWatch Logs"]
```

The AWS deployment uses CodePipeline from GitHub, container images in ECR, blue/green ECS deployments through CodeDeploy, and runtime services for storage, retrieval, secrets, and observability. DynamoDB is not part of the new deployment path; RDS PostgreSQL is used instead.

## LLD 1: Online Chat Request

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as FastAPI /chat
    participant S as SupervisorAgent
    participant D as DeterministicLookupAgent
    participant R as RAGAgent
    participant P as PolicyAgent
    participant C as CatalogAgent
    participant X as SafetyAgent
    participant Y as SynthesisAgent

    U->>F: Ask a clinical knowledge question
    F->>A: POST /chat
    A->>S: Start multi-agent graph
    S->>D: Route exact row/count/list questions when needed
    S->>R: Route document content questions when needed
    S->>P: Route policy/SOP/guideline questions when needed
    S->>C: Route document inventory questions when needed
    S->>X: Route safety/escalation checks when needed
    S->>Y: Send accumulated specialist evidence
    Y->>A: Final consistent answer
    A->>F: ChatResponse with agent metadata
```

Every online request enters the supervisor-led graph. Deterministic lookup is a normal specialist path, not a preflight shortcut. The supervisor may call more than one specialist for multipart questions before synthesis.

## LLD 2: Deterministic Lookup

```mermaid
flowchart TD
    Q["User asks: who is on call, list medicines, available ventilators"] --> Agent["DeterministicLookupAgent"]
    Agent --> Tool["deterministic_healthcare_lookup tool"]
    Tool --> Planner["Lookup intent and table planner"]
    Planner --> DB["PostgreSQL healthcare lookup tables"]
    DB --> Rows["Matched rows, counts, or unique values"]
    Rows --> Formatter["Structured deterministic response formatter"]
    Formatter --> Evidence["Specialist evidence for synthesis"]
```

CSV rows are inserted during upload and ingestion. Query execution reads existing PostgreSQL rows; it does not append rows during chat.

Important lookup behavior:

- Availability questions filter to the requested equipment or medicine.
- On-call questions search staff schedule rows where `on_call=Yes`.
- Listing questions return unique instances first.
- Large lookup results use a concise first section and an expandable full-details section.
- The specialist returns structured evidence so synthesis can keep answer format consistent.

## LLD 3: Document Ingest And Retrieval

```mermaid
flowchart TD
    Upload["Admin uploads document or CSV"] --> API["FastAPI admin endpoint"]
    API --> Store["DocumentStore"]
    Store --> S3["S3 raw document and manifest"]
    Store --> RDS["Postgres metadata and CSV rows"]
    API --> Ingest["Ingestion pipeline"]
    Ingest --> Chunk["Chunk and normalize text"]
    Chunk --> Embed["Azure OpenAI embeddings"]
    Embed --> Index["OpenSearch Serverless index"]
    Index --> Retrieval["RAG and Policy retrieval tools"]
```

Documents are stored in S3 and indexed into OpenSearch Serverless. CSV uploads populate PostgreSQL lookup tables during upload/ingestion, not during chat.

## LLD 4: Tool Execution Boundary

```mermaid
flowchart LR
    Specialist["Specialist agent selects tool"] --> Registry["Tool registry"]
    Registry --> Mode{"TOOL_EXECUTION_BACKEND"}
    Mode -->|local| Local["Local Python tool implementation"]
    Mode -->|mcp| Client["FastMCP client"]
    Client --> Server["External MCP tool server"]
    Local --> Result["Tool result"]
    Server --> Result
    Result --> Specialist
```

The supervisor and specialist agents see stable tool names. The execution backend decides whether the tool runs in-process or is forwarded to a FastMCP server.

## LLD 5: CI/CD Deployment

```mermaid
flowchart LR
    Dev["Developer commit"] --> GitHub["GitHub"]
    GitHub --> Source["CodePipeline source"]
    Source --> Build["CodeBuild buildspec"]
    Build --> Images["ECR images"]
    Build --> Artifacts["Task definition and AppSpec artifacts"]
    Artifacts --> Deploy["CodeDeploy ECS blue/green"]
    Deploy --> ECS["ECS backend and frontend services"]
    ECS --> ALB["Application Load Balancer"]
```

CodeBuild renders deployment artifacts with the runtime values produced by CloudFormation. CodeDeploy then swaps traffic between blue and green target groups.

## LLD 6: Observability And Evaluation

```mermaid
flowchart TD
    Chat["Chat request"] --> Trace["Langfuse trace"]
    Chat --> Metadata["Agent flow, tools, latencies, errors"]
    Metadata --> Postgres["Postgres chat history and trace outbox"]
    Trace --> Langfuse["Langfuse"]
    Langfuse --> Ragas["RAGAS evaluation"]
    Postgres --> Dashboard["Admin dashboard"]
```

The backend saves agent flow, agents used, supervisor decisions, tool names, latency fields, and errors. If Langfuse publishing fails, pending trace updates are written to the Postgres outbox for retry.

## Editable Diagram Sources

The corresponding editable draw.io files are:

- `docs/aws_hld_stakeholder.drawio`
- `docs/aws_hld_technical.drawio`
- `docs/aws_lld_processes.drawio`
- `docs/aws_lld_lookup_ingest_observability.drawio`

The generated PDF version is:

- `docs/aws_multi_agent_architecture.pdf`
