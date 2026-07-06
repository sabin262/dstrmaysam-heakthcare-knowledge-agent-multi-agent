import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT_DIR = process.env.OUTPUT_DIR
  ? path.resolve(process.env.OUTPUT_DIR)
  : path.resolve(process.cwd());
const PREVIEW_DIR = path.join(OUT_DIR, "previews");

const W = 1280;
const H = 720;
const C = {
  ink: "#111111",
  muted: "#555555",
  faint: "#EDEDED",
  rule: "#B8BCC4",
  accent: "#FF6B35",
  accent2: "#0E7490",
  panel: "#F6F6F6",
  white: "#FFFFFF",
  green: "#166534",
};

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function xmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function makeDrawio(name, nodes, edges) {
  const nodeXml = nodes
    .map((n) => {
      const style = [
        "rounded=1",
        "whiteSpace=wrap",
        "html=1",
        `fillColor=${n.fill || "#FFFFFF"}`,
        `strokeColor=${n.stroke || "#111111"}`,
        `fontColor=${n.font || "#111111"}`,
        "fontSize=14",
        "spacing=10",
      ].join(";");
      return `<mxCell id="${xmlEscape(n.id)}" value="${xmlEscape(n.label)}" style="${style}" vertex="1" parent="1"><mxGeometry x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" as="geometry"/></mxCell>`;
    })
    .join("");
  const edgeXml = edges
    .map((e, idx) => {
      const label = e.label ? ` value="${xmlEscape(e.label)}"` : "";
      return `<mxCell id="edge-${idx + 1}"${label} style="endArrow=block;html=1;rounded=0;strokeColor=${e.color || "#555555"};fontColor=#555555;" edge="1" parent="1" source="${xmlEscape(e.from)}" target="${xmlEscape(e.to)}"><mxGeometry relative="1" as="geometry"/></mxCell>`;
    })
    .join("");
  return `<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" modified="2026-07-06T00:00:00.000Z" agent="Codex" version="24.7.17">
  <diagram id="${xmlEscape(name.toLowerCase().replaceAll(" ", "-"))}" name="${xmlEscape(name)}">
    <mxGraphModel dx="1280" dy="720" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1280" pageHeight="720" math="0" shadow="0">
      <root><mxCell id="0"/><mxCell id="1" parent="0"/>${nodeXml}${edgeXml}</root>
    </mxGraphModel>
  </diagram>
</mxfile>
`;
}

async function writeDrawioFiles() {
  const stakeholderNodes = [
    { id: "users", label: "Hospital teams\nChat, CRM, Documents, WhatsApp", x: 40, y: 220, w: 210, h: 90, fill: "#FFF7ED", stroke: C.accent },
    { id: "app", label: "Healthcare knowledge app\nOne governed front door", x: 330, y: 210, w: 230, h: 110, fill: "#FFFFFF" },
    { id: "agents", label: "Multi-agent reasoning\nSupervisor + specialists", x: 650, y: 190, w: 230, h: 150, fill: "#F0FDFA", stroke: C.accent2 },
    { id: "sources", label: "Trusted sources\nPolicies, documents, CRM tables", x: 970, y: 155, w: 230, h: 220, fill: "#F6F6F6" },
    { id: "answers", label: "Grounded answers\nCitations, role-based access, audit trail", x: 650, y: 450, w: 230, h: 120, fill: "#F7FEE7", stroke: "#166534" },
  ];
  const stakeholderEdges = [
    { from: "users", to: "app" },
    { from: "app", to: "agents" },
    { from: "agents", to: "sources" },
    { from: "sources", to: "answers" },
    { from: "answers", to: "users" },
  ];

  const technicalNodes = [
    { id: "ui", label: "Streamlit UI\nChat, CRM, documents, evaluations, settings", x: 40, y: 80, w: 250, h: 100, fill: "#FFF7ED", stroke: C.accent },
    { id: "api", label: "FastAPI backend\nAuth, admin, chat, Twilio webhook", x: 380, y: 80, w: 250, h: 100 },
    { id: "graph", label: "LangGraph agents\nSupervisor, specialists, synthesis, safety", x: 720, y: 80, w: 250, h: 100, fill: "#F0FDFA", stroke: C.accent2 },
    { id: "router", label: "Tool execution router\nLocal tools or MCP tools", x: 720, y: 260, w: 250, h: 100 },
    { id: "mcp", label: "Shared MCP server\nExternal tool execution service", x: 1030, y: 260, w: 210, h: 100, fill: "#F6F6F6" },
    { id: "pg", label: "Postgres\nCRM, lookup, chat, eval history", x: 80, y: 470, w: 210, h: 90 },
    { id: "s3", label: "S3 + manifest\nDocument storage and metadata", x: 370, y: 470, w: 210, h: 90 },
    { id: "os", label: "OpenSearch / Chroma\nIndexed chunks for retrieval", x: 660, y: 470, w: 210, h: 90 },
    { id: "aoai", label: "Azure OpenAI\nSupervisor, synthesis, embeddings", x: 950, y: 470, w: 210, h: 90 },
  ];
  const technicalEdges = [
    { from: "ui", to: "api" },
    { from: "api", to: "graph" },
    { from: "graph", to: "router" },
    { from: "router", to: "mcp" },
    { from: "router", to: "pg" },
    { from: "router", to: "s3" },
    { from: "router", to: "os" },
    { from: "graph", to: "aoai" },
  ];

  const deploymentNodes = [
    { id: "internet", label: "Users and Twilio", x: 40, y: 60, w: 190, h: 70, fill: "#FFF7ED", stroke: C.accent },
    { id: "alb", label: "Healthcare public ALB\nFrontend, backend, optional MCP listener", x: 310, y: 50, w: 260, h: 90 },
    { id: "ecs", label: "Healthcare ECS cluster\nFrontend + backend services", x: 650, y: 50, w: 260, h: 90 },
    { id: "mcp1", label: "Healthcare MCP service\nSame healthcare VPC", x: 990, y: 50, w: 220, h: 90, fill: "#F6F6F6" },
    { id: "rds", label: "RDS Postgres\nOperational data and history", x: 180, y: 280, w: 220, h: 90 },
    { id: "s3", label: "S3 documents\nRaw files and manifest", x: 460, y: 280, w: 220, h: 90 },
    { id: "os", label: "OpenSearch Serverless\nPolicy and document chunks", x: 740, y: 280, w: 220, h: 90 },
    { id: "secrets", label: "Secrets Manager\nApp, Azure, MCP settings", x: 1020, y: 280, w: 220, h: 90 },
    { id: "shared", label: "Shared MCP stack\nSeparate VPC, ECS service, internal ALB", x: 300, y: 520, w: 290, h: 100, fill: "#F0FDFA", stroke: C.accent2 },
    { id: "tgw", label: "Transit Gateway\nPrivate route between VPCs", x: 700, y: 530, w: 240, h: 80 },
    { id: "pipeline", label: "CodePipeline + CodeBuild\nBuild images and update ECS", x: 980, y: 520, w: 250, h: 100, fill: "#FFF7ED", stroke: C.accent },
  ];
  const deploymentEdges = [
    { from: "internet", to: "alb" },
    { from: "alb", to: "ecs" },
    { from: "alb", to: "mcp1" },
    { from: "ecs", to: "rds" },
    { from: "ecs", to: "s3" },
    { from: "ecs", to: "os" },
    { from: "ecs", to: "secrets" },
    { from: "shared", to: "tgw" },
    { from: "tgw", to: "rds" },
    { from: "pipeline", to: "ecs" },
    { from: "pipeline", to: "mcp1" },
  ];

  const workflowNodes = [
    { id: "query", label: "User asks a question", x: 50, y: 70, w: 180, h: 70, fill: "#FFF7ED", stroke: C.accent },
    { id: "supervisor", label: "SupervisorAgent\nChooses specialist work", x: 300, y: 55, w: 220, h: 100, fill: "#F0FDFA", stroke: C.accent2 },
    { id: "det", label: "DeterministicLookupAgent\nPostgres facts", x: 650, y: 40, w: 220, h: 80 },
    { id: "policy", label: "PolicyAgent\nGuidelines and SOPs", x: 650, y: 140, w: 220, h: 80 },
    { id: "rag", label: "RAGAgent\nGeneral document content", x: 650, y: 240, w: 220, h: 80 },
    { id: "catalog", label: "CatalogAgent\nDocument inventory", x: 650, y: 340, w: 220, h: 80 },
    { id: "safety", label: "SafetyAgent\nRisk and PHI review", x: 650, y: 440, w: 220, h: 80 },
    { id: "tools", label: "Specialist selects allowed tools\nLocal or MCP execution", x: 960, y: 220, w: 230, h: 120, fill: "#F6F6F6" },
    { id: "synthesis", label: "SynthesisAgent\nOne final answer with evidence", x: 960, y: 470, w: 230, h: 90, fill: "#F7FEE7", stroke: "#166534" },
  ];
  const workflowEdges = [
    { from: "query", to: "supervisor" },
    { from: "supervisor", to: "det" },
    { from: "supervisor", to: "policy" },
    { from: "supervisor", to: "rag" },
    { from: "supervisor", to: "catalog" },
    { from: "supervisor", to: "safety" },
    { from: "det", to: "tools" },
    { from: "policy", to: "tools" },
    { from: "rag", to: "tools" },
    { from: "catalog", to: "tools" },
    { from: "tools", to: "supervisor", label: "report" },
    { from: "safety", to: "synthesis" },
    { from: "supervisor", to: "synthesis" },
  ];

  const dataNodes = [
    { id: "upload", label: "Document or CSV upload", x: 60, y: 90, w: 200, h: 70, fill: "#FFF7ED", stroke: C.accent },
    { id: "classify", label: "Classification and metadata\nCategory, type, access roles", x: 340, y: 70, w: 240, h: 110 },
    { id: "tables", label: "Supported CSVs update\nPostgres operational tables", x: 680, y: 60, w: 240, h: 90 },
    { id: "chunks", label: "Documents are chunked\nand indexed for retrieval", x: 680, y: 180, w: 240, h: 90 },
    { id: "manifest", label: "Manifest tracks files and table metadata", x: 340, y: 260, w: 240, h: 90, fill: "#F6F6F6" },
    { id: "chat", label: "Chat retrieves facts and evidence\nfrom tables, catalog, and chunks", x: 680, y: 340, w: 240, h: 100, fill: "#F0FDFA", stroke: C.accent2 },
    { id: "evals", label: "Dashboard and evaluations\nmeasure routing, sources, safety, latency", x: 340, y: 480, w: 250, h: 100, fill: "#F7FEE7", stroke: "#166534" },
  ];
  const dataEdges = [
    { from: "upload", to: "classify" },
    { from: "classify", to: "tables" },
    { from: "classify", to: "chunks" },
    { from: "classify", to: "manifest" },
    { from: "tables", to: "chat" },
    { from: "chunks", to: "chat" },
    { from: "manifest", to: "chat" },
    { from: "chat", to: "evals" },
  ];

  await fs.writeFile(path.join(OUT_DIR, "stakeholder_high_level_architecture.drawio"), makeDrawio("Stakeholder High Level Architecture", stakeholderNodes, stakeholderEdges));
  await fs.writeFile(path.join(OUT_DIR, "technical_high_level_architecture.drawio"), makeDrawio("Technical High Level Architecture", technicalNodes, technicalEdges));
  await fs.writeFile(path.join(OUT_DIR, "aws_deployment_architecture.drawio"), makeDrawio("AWS Deployment Architecture", deploymentNodes, deploymentEdges));
  await fs.writeFile(path.join(OUT_DIR, "multiagent_workflow.drawio"), makeDrawio("Multi-Agent Workflow", workflowNodes, workflowEdges));
  await fs.writeFile(path.join(OUT_DIR, "data_and_tool_flow.drawio"), makeDrawio("Data And Tool Flow", dataNodes, dataEdges));
}

function addText(slide, text, pos, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: pos,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: style.fontSize ?? 20,
    bold: style.bold ?? false,
    color: style.color ?? C.ink,
    alignment: style.alignment ?? "left",
    fontFace: "Helvetica Neue",
  };
  return shape;
}

function addTitle(slide, title, kicker = "") {
  if (kicker) {
    addText(slide, kicker.toUpperCase(), { left: 42, top: 32, width: 420, height: 24 }, { fontSize: 14, bold: true, color: C.muted });
  }
  addText(slide, title, { left: 42, top: 66, width: 1080, height: 84 }, { fontSize: 39, bold: true, color: C.ink });
  slide.shapes.add({
    geometry: "rect",
    position: { left: 42, top: 158, width: 1196, height: 1 },
    fill: C.rule,
    line: { style: "solid", fill: C.rule, width: 0 },
  });
}

function addFooter(slide, n) {
  addText(slide, "dstrmaysam healthcare knowledge multi-agent", { left: 42, top: 670, width: 520, height: 24 }, { fontSize: 13, color: C.muted });
  addText(slide, String(n).padStart(2, "0"), { left: 1190, top: 670, width: 48, height: 24 }, { fontSize: 13, color: C.muted, alignment: "right" });
}

function addBox(slide, label, pos, options = {}) {
  const shape = slide.shapes.add({
    geometry: options.geometry || "roundRect",
    name: options.name || label,
    position: pos,
    fill: options.fill || C.white,
    line: { style: "solid", fill: options.stroke || C.ink, width: options.width || 1 },
    borderRadius: "rounded-lg",
  });
  shape.text = label;
  shape.text.style = {
    fontSize: options.fontSize || 18,
    bold: options.bold ?? true,
    color: options.color || C.ink,
    alignment: "center",
    fontFace: "Helvetica Neue",
  };
  return shape;
}

function addBullets(slide, bullets, pos, options = {}) {
  const body = bullets.map((b) => `- ${b}`).join("\n");
  return addText(slide, body, pos, {
    fontSize: options.fontSize || 20,
    color: options.color || C.ink,
    bold: options.bold || false,
  });
}

function addMetric(slide, value, label, pos, accent = C.accent) {
  slide.shapes.add({
    geometry: "rect",
    position: pos,
    fill: C.panel,
    line: { style: "solid", fill: "none", width: 0 },
  });
  addText(slide, value, { left: pos.left + 20, top: pos.top + 28, width: pos.width - 40, height: 48 }, { fontSize: 32, bold: true, color: accent });
  addText(slide, label, { left: pos.left + 20, top: pos.top + 86, width: pos.width - 40, height: 64 }, { fontSize: 18, color: C.ink });
}

function addChallenge(slide, title, label, pos, accent = C.accent) {
  slide.shapes.add({
    geometry: "rect",
    position: pos,
    fill: C.panel,
    line: { style: "solid", fill: "none", width: 0 },
  });
  addText(slide, title, { left: pos.left + 22, top: pos.top + 24, width: pos.width - 44, height: 44 }, { fontSize: 27, bold: true, color: accent });
  addText(slide, label, { left: pos.left + 22, top: pos.top + 82, width: pos.width - 44, height: 78 }, { fontSize: 18, color: C.ink });
}

function addLine(slide, from, to, options = {}) {
  return slide.shapes.add({
    geometry: "line",
    position: { left: from.x, top: from.y, width: to.x - from.x, height: to.y - from.y },
    fill: "none",
    line: { style: "solid", fill: options.color || C.muted, width: options.width || 2, beginArrowType: "none", endArrowType: "triangle" },
  });
}

function slideTitle(presentation, title, kicker) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addTitle(slide, title, kicker);
  addFooter(slide, presentation.slides.items.length);
  return slide;
}

function buildDeck() {
  const deck = Presentation.create({ slideSize: { width: W, height: H } });

  let s = deck.slides.add();
  s.background.fill = C.white;
  addText(s, "Healthcare Knowledge\nMulti-Agent System", { left: 42, top: 92, width: 780, height: 180 }, { fontSize: 58, bold: true });
  addText(s, "A short demo deck for a governed hospital knowledge assistant that answers from live operational data, indexed documents, and specialist agents.", { left: 42, top: 330, width: 690, height: 100 }, { fontSize: 24, color: C.muted });
  addBox(s, "15 minute presentation and demo", { left: 822, top: 120, width: 350, height: 120 }, { fill: C.panel, stroke: "none", fontSize: 25 });
  addBox(s, "Built from the current codebase", { left: 822, top: 280, width: 350, height: 120 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 25 });
  addFooter(s, 1);

  s = slideTitle(deck, "The problem is trusted hospital knowledge is spread across too many places", "Problem statement");
  addBullets(
    s,
    [
      "Staff need quick answers from policies, rotas, equipment records, patient context, and document repositories.",
      "Searching each system separately slows decisions and increases the chance of using stale information.",
      "Operational facts and policy guidance need different handling, but users should not have to know where to search.",
      "Governance matters: answers must respect roles, safety risk, source evidence, and auditability.",
    ],
    { left: 76, top: 210, width: 720, height: 320 },
    { fontSize: 24 },
  );
  addMetric(s, "One front door", "for chat, documents, CRM, evaluations, and admin controls", { left: 900, top: 230, width: 260, height: 170 });
  addMetric(s, "Grounded answers", "from Postgres tables and indexed evidence rather than memory alone", { left: 900, top: 430, width: 260, height: 170 }, C.accent2);

  s = slideTitle(deck, "The system gives staff a single governed way to ask and act", "Stakeholder architecture");
  const u = addBox(s, "Hospital teams\nChat, CRM, Documents,\nWhatsApp", { left: 62, top: 300, width: 210, height: 110 }, { fill: "#FFF7ED", stroke: C.accent });
  const app = addBox(s, "Healthcare\nknowledge app", { left: 338, top: 288, width: 210, height: 134 }, { fill: C.white });
  const agents = addBox(s, "Multi-agent\nreasoning", { left: 628, top: 260, width: 220, height: 190 }, { fill: "#F0FDFA", stroke: C.accent2 });
  const src = addBox(s, "Trusted sources\nPolicies\nDocuments\nCRM tables", { left: 936, top: 250, width: 230, height: 210 }, { fill: C.panel });
  addLine(s, { x: 274, y: 355 }, { x: 338, y: 355 });
  addLine(s, { x: 548, y: 355 }, { x: 628, y: 355 });
  addLine(s, { x: 848, y: 355 }, { x: 936, y: 355 });
  addText(s, "The user sees a simple answer. The system decides whether it needs operational data, document evidence, policy retrieval, catalog metadata, or safety review.", { left: 106, top: 520, width: 990, height: 70 }, { fontSize: 22, color: C.muted, alignment: "center" });

  s = slideTitle(deck, "AWS separates the healthcare app from shared tool execution", "Deployment architecture");
  addBox(s, "Users + Twilio", { left: 42, top: 235, width: 150, height: 70 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 17 });
  addBox(s, "Healthcare public ALB", { left: 250, top: 220, width: 210, height: 100 }, { fontSize: 18 });
  addBox(s, "ECS services\nFrontend + backend", { left: 530, top: 210, width: 220, height: 120 }, { fill: "#F0FDFA", stroke: C.accent2, fontSize: 18 });
  addBox(s, "RDS Postgres", { left: 840, top: 120, width: 170, height: 70 }, { fill: C.panel, fontSize: 17 });
  addBox(s, "S3 documents", { left: 840, top: 225, width: 170, height: 70 }, { fill: C.panel, fontSize: 17 });
  addBox(s, "OpenSearch\nServerless", { left: 840, top: 330, width: 170, height: 70 }, { fill: C.panel, fontSize: 17 });
  addBox(s, "Secrets\nManager", { left: 840, top: 435, width: 170, height: 70 }, { fill: C.panel, fontSize: 17 });
  addBox(s, "Shared MCP stack\nECS + internal ALB", { left: 240, top: 500, width: 260, height: 90 }, { fill: "#F6F6F6", stroke: C.ink, fontSize: 18 });
  addBox(s, "Transit Gateway\nprivate VPC route", { left: 565, top: 505, width: 220, height: 80 }, { fill: C.white, fontSize: 17 });
  addBox(s, "CodePipeline\nbuilds and deploys", { left: 1040, top: 250, width: 160, height: 110 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 17 });
  addLine(s, { x: 192, y: 270 }, { x: 250, y: 270 });
  addLine(s, { x: 460, y: 270 }, { x: 530, y: 270 });
  addLine(s, { x: 750, y: 260 }, { x: 840, y: 155 });
  addLine(s, { x: 750, y: 270 }, { x: 840, y: 260 });
  addLine(s, { x: 750, y: 280 }, { x: 840, y: 365 });
  addLine(s, { x: 750, y: 290 }, { x: 840, y: 470 });
  addLine(s, { x: 500, y: 545 }, { x: 565, y: 545 });
  addLine(s, { x: 785, y: 545 }, { x: 840, y: 155 });

  s = slideTitle(deck, "The application combines chat, operations, documents, and assurance", "System overview");
  addMetric(s, "Chat", "Multi-agent answers with sources, routing trace, and optional WhatsApp entry point", { left: 54, top: 210, width: 260, height: 170 }, C.accent);
  addMetric(s, "Hospital CRM", "Patients, doctors, departments, schedules, appointments, finance, and table CRUD", { left: 366, top: 210, width: 260, height: 170 }, C.accent2);
  addMetric(s, "Documents", "Upload, metadata edit, chunking, indexing, catalog search, and role access", { left: 678, top: 210, width: 260, height: 170 }, C.green);
  addMetric(s, "Evaluations", "Golden and stress tests for agents, tools, sources, safety, and latency", { left: 990, top: 210, width: 220, height: 170 }, C.ink);
  addText(s, "Admins can change tool execution mode, review query traces, track costs and latency, and manage the metadata that drives routing quality.", { left: 110, top: 470, width: 1040, height: 90 }, { fontSize: 24, color: C.muted, alignment: "center" });

  s = slideTitle(deck, "Supervisor chooses specialists; specialists choose their tools", "Multi-agent workflow");
  addBox(s, "User question", { left: 55, top: 315, width: 160, height: 70 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 17 });
  addBox(s, "SupervisorAgent\nselects specialist work", { left: 290, top: 285, width: 220, height: 130 }, { fill: "#F0FDFA", stroke: C.accent2, fontSize: 18 });
  const specialistLabels = [
    ["DeterministicLookupAgent\nPostgres facts", 590, 175],
    ["PolicyAgent\nGuidelines and SOPs", 590, 275],
    ["RAGAgent\nGeneral document evidence", 590, 375],
    ["CatalogAgent\nDocument inventory", 850, 225],
    ["SafetyAgent\nRisk and PHI review", 850, 345],
  ];
  for (const [label, left, top] of specialistLabels) {
    addBox(s, label, { left, top, width: 220, height: 76 }, { fill: C.white, fontSize: 16 });
  }
  addBox(s, "SynthesisAgent\nwrites one final answer", { left: 995, top: 490, width: 220, height: 86 }, { fill: "#F7FEE7", stroke: C.green, fontSize: 17 });
  addLine(s, { x: 215, y: 350 }, { x: 290, y: 350 });
  addLine(s, { x: 510, y: 345 }, { x: 590, y: 213 });
  addLine(s, { x: 510, y: 350 }, { x: 590, y: 313 });
  addLine(s, { x: 510, y: 355 }, { x: 590, y: 413 });
  addLine(s, { x: 510, y: 360 }, { x: 850, y: 263 });
  addLine(s, { x: 510, y: 365 }, { x: 850, y: 383 });
  addLine(s, { x: 1070, y: 421 }, { x: 1070, y: 490 });
  addText(s, "Each specialist validates its evidence and returns a report. The supervisor arbitrates reports before the final answer is shown.", { left: 110, top: 585, width: 1000, height: 55 }, { fontSize: 21, color: C.muted, alignment: "center" });

  s = slideTitle(deck, "Tool execution can move without changing the user experience", "Tools and MCP");
  addBox(s, "Backend agents\nreason and select tools", { left: 82, top: 230, width: 250, height: 110 }, { fill: "#F0FDFA", stroke: C.accent2 });
  addBox(s, "Tool router\nlocal or MCP mode", { left: 412, top: 230, width: 230, height: 110 }, { fill: C.white });
  addBox(s, "Shared healthcare tools package\nsame lookup and retrieval logic", { left: 722, top: 210, width: 260, height: 150 }, { fill: C.panel });
  addBox(s, "MCP server\nexecutes tools for this and future projects", { left: 1030, top: 230, width: 190, height: 110 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 17 });
  addLine(s, { x: 332, y: 285 }, { x: 412, y: 285 });
  addLine(s, { x: 642, y: 285 }, { x: 722, y: 285 });
  addLine(s, { x: 982, y: 285 }, { x: 1030, y: 285 });
  addBullets(
    s,
    [
      "Agent reasoning stays in the healthcare backend.",
      "MCP only executes the selected tool and returns the result.",
      "Settings can switch local and MCP execution without changing the chat API.",
      "The dashboard records where tool calls actually happened.",
    ],
    { left: 170, top: 440, width: 900, height: 150 },
    { fontSize: 23 },
  );

  s = slideTitle(deck, "A short demo can show the full value chain", "Suggested demo path");
  addBox(s, "1\nAsk an operational question\nwho is on call today?", { left: 70, top: 225, width: 230, height: 150 }, { fill: "#FFF7ED", stroke: C.accent, fontSize: 19 });
  addBox(s, "2\nAsk a policy question\nhow do I report an incident?", { left: 370, top: 225, width: 230, height: 150 }, { fill: "#F0FDFA", stroke: C.accent2, fontSize: 19 });
  addBox(s, "3\nAsk a catalog question\nwhat guideline documents exist?", { left: 670, top: 225, width: 230, height: 150 }, { fill: C.panel, fontSize: 19 });
  addBox(s, "4\nOpen trace and evaluations\nverify agents, tools, sources", { left: 970, top: 225, width: 230, height: 150 }, { fill: "#F7FEE7", stroke: C.green, fontSize: 19 });
  addText(s, "The point of the demo is not that the assistant talks. It is that the answer shows where it came from, which specialist handled it, and how the system can be tested.", { left: 120, top: 475, width: 1040, height: 80 }, { fontSize: 24, color: C.muted, alignment: "center" });

  s = slideTitle(deck, "The solution addresses the business problem through trust and speed", "Business impact");
  addBullets(
    s,
    [
      "Faster response: common operational and policy questions can be answered from one place.",
      "Better governance: role-based access, PHI handling, safety review, citations, and trace metadata are built into the workflow.",
      "Less duplication: local and MCP tools share the same core healthcare tool package.",
      "Measurable quality: golden dataset and stress tests check routing, tools, sources, safety, and latency.",
      "Future ready: tools can move to shared MCP services while the specialist agent workflow remains in the healthcare backend.",
    ],
    { left: 90, top: 210, width: 980, height: 330 },
    { fontSize: 24 },
  );

  s = slideTitle(deck, "The main challenges are manageable, but they need active ownership", "Challenges");
  addChallenge(s, "Routing quality", "Catalog, policy, RAG, and database paths need continuous test coverage.", { left: 60, top: 215, width: 260, height: 170 }, C.accent);
  addChallenge(s, "Evidence quality", "Good answers depend on metadata, chunking, fresh sources, and complete tables.", { left: 365, top: 215, width: 260, height: 170 }, C.accent2);
  addChallenge(s, "Latency and cost", "More specialist reasoning improves assurance but can add LLM calls.", { left: 670, top: 215, width: 260, height: 170 }, C.green);
  addChallenge(s, "Cloud networking", "MCP, RDS, ALB, secrets, and VPC routing must stay aligned.", { left: 975, top: 215, width: 230, height: 170 }, C.ink);
  addText(s, "These are not blockers; they are operating disciplines. The current dashboard and evaluations page are designed to expose them early.", { left: 120, top: 475, width: 1030, height: 90 }, { fontSize: 24, color: C.muted, alignment: "center" });

  s = slideTitle(deck, "The next phase is production hardening and wider tool reuse", "Recommended next steps");
  addBullets(
    s,
    [
      "Add HTTPS with a managed domain and certificate for user-facing and webhook endpoints.",
      "Keep expanding the golden dataset as new documents, CRM tables, and query patterns are added.",
      "Stabilise shared MCP deployment so every project gets the same tool quality with project-specific secrets.",
      "Tune chunking and retrieval using real failure cases from evaluations rather than generic benchmarks.",
      "Add monitoring alerts for RDS connectivity, OpenSearch failures, MCP fallback, LLM rate limits, latency, and cost.",
    ],
    { left: 94, top: 210, width: 980, height: 330 },
    { fontSize: 24 },
  );
  addText(s, "The system is already structured for this path: agents stay in the backend, tools are shared, and quality is measured at the full-system level.", { left: 110, top: 565, width: 1030, height: 64 }, { fontSize: 23, color: C.muted, alignment: "center" });

  return deck;
}

async function writeSystemOverview() {
  const md = `# Healthcare Knowledge Multi-Agent System Overview

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

- FastAPI app: \`backend/app/api/app.py\`
  - Auth and user management.
  - Chat endpoint: \`POST /chat\`.
  - Document upload and ingestion endpoints.
  - CRM CRUD endpoints.
  - Dashboard and evaluation endpoints.
  - Twilio webhook endpoint: \`POST /twilio/whatsapp/webhook\`.
- Multi-agent orchestration: \`backend/app/agents/knowledge_agent.py\`
  - Uses LangGraph to run the in-process multi-agent workflow.
  - Public API shape remains stable while internal routing is handled by agents.
- Tool execution: \`backend/app/tool_execution.py\`
  - Routes tool calls either to local tool execution or to an MCP server.
  - Records actual execution location and fallback status for dashboard visibility.
- Shared healthcare tool package:
  - \`backend/packages/healthcare_tools_core/src/healthcare_tools_core\`
  - Shared by the healthcare backend and MCP server so table lookup and retrieval logic stay aligned.

## Agents

- \`SupervisorAgent\`: selects the next specialist agent and arbitrates reports.
- \`DeterministicLookupAgent\`: handles exact Postgres-backed operational facts such as patients, appointments, rota, departments, wards, equipment, contacts, formulary, finance, counts, lists, and row-level queries.
- \`PolicyAgent\`: handles policies, SOPs, pathways, compliance, governance, retention, research, and other policy evidence questions.
- \`RAGAgent\`: handles broader document-content retrieval that is not specifically a policy inventory or exact database lookup.
- \`CatalogAgent\`: handles document inventory and metadata questions.
- \`SafetyAgent\`: reviews urgent, risky, PHI-sensitive, escalation, or clinical-safety-sensitive responses.
- \`SynthesisAgent\`: produces the final user-facing answer from specialist reports.

## Tool Model

The current architecture keeps reasoning in the healthcare backend. Specialists choose tools, and the tool execution router decides whether the selected tool runs locally or through MCP.

Healthcare tools include:

- \`postgres_deterministic_lookup\`
- \`document_search\`
- \`rag_search\`
- \`policy_search\`
- \`catalogue_search\`
- \`document_catalog\`
- \`safety_guard\`
- compatibility wrappers such as \`calendar_rota_lookup\`, \`formulary_table_lookup\`, and \`table_lookup\`

In MCP mode, the backend sends the selected tool name and payload to the MCP server. The MCP server executes the tool and returns the result. The backend still owns supervisor routing, specialist selection, synthesis, safety orchestration, and public response formatting.

## Data And Retrieval

- Postgres stores operational CRM data, lookup tables, chat history, evaluation history, and seeded hospital data.
- S3 stores uploaded documents and metadata/manifest assets in AWS mode.
- OpenSearch Serverless stores indexed document chunks in AWS mode.
- Local mode uses local equivalents where configured, including local Postgres and local vector storage.
- Supported CSV uploads update known Postgres tables rather than creating arbitrary CSV row blobs.
- Document ingestion preserves metadata, deletes old chunks for changed documents, then writes fresh chunks.

## AWS Deployment

The healthcare stack is defined in \`infra/aws-foundation.yml\`. It creates or configures:

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

The MCP server lives in a separate repository at \`C:\\Users\\Sabin\\Documents\\ITC Projects\\MCP-Tools\`.

The shared stack template at \`MCP-Tools\\infra\\shared-mcp-stack.yml\` creates:

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
`;
  await fs.writeFile(path.join(OUT_DIR, "system_overview.md"), md);
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  await writeDrawioFiles();
  await writeSystemOverview();

  const deck = buildDeck();
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(PREVIEW_DIR, `${stem}.png`), await deck.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(PREVIEW_DIR, `${stem}.layout.json`), await layout.text());
  }
  await writeBlob(path.join(PREVIEW_DIR, "deck-montage.webp"), await deck.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(path.join(OUT_DIR, "healthcare_multi_agent_demo_deck.pptx"));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
