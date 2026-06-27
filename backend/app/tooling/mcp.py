from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from ..healthcare import HealthcareUserContext
from .base import AgentTool


@dataclass(frozen=True)
class McpToolClientConfig:
    server_url: str
    timeout_seconds: float = 20.0


@dataclass(frozen=True)
class McpToolRequestContext:
    user: HealthcareUserContext
    app_context: dict[str, Any] = field(default_factory=dict)


def build_mcp_tool_registry(
    local_tool_contracts: list[AgentTool],
    *,
    config: McpToolClientConfig,
    context: McpToolRequestContext,
) -> list[AgentTool]:
    return [
        AgentTool(
            name=tool.name,
            description=tool.description,
            run=_make_mcp_runner(tool.name, config=config, context=context),
        )
        for tool in local_tool_contracts
    ]


def _make_mcp_runner(
    tool_name: str,
    *,
    config: McpToolClientConfig,
    context: McpToolRequestContext,
):
    def run(query: str) -> str:
        if not config.server_url:
            return json.dumps(
                {
                    "error": "MCP tool execution is enabled but MCP_TOOL_SERVER_URL is not configured.",
                    "tool": tool_name,
                },
                indent=2,
            )
        payload = _tool_payload(tool_name, query, context)
        try:
            return _run_async(_call_fastmcp_tool(config, tool_name, payload))
        except Exception as exc:
            return json.dumps(
                {
                    "error": f"MCP tool execution failed: {type(exc).__name__}: {exc}",
                    "tool": tool_name,
                },
                indent=2,
            )

    return run


def _tool_payload(tool_name: str, query: str, context: McpToolRequestContext) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "query": query,
        "user": {
            "user_id": context.user.user_id,
            "roles": list(context.user.roles),
            "departments": list(context.user.departments),
            "password_change_required": context.user.password_change_required,
        },
        "app_context": dict(context.app_context),
    }


async def _call_fastmcp_tool(config: McpToolClientConfig, tool_name: str, payload: dict[str, Any]) -> str:
    try:
        from fastmcp import Client
    except Exception as exc:  # pragma: no cover - depends on optional package installation
        raise RuntimeError("fastmcp is not installed. Install backend requirements to use MCP tools.") from exc

    async def call() -> Any:
        async with Client(config.server_url) as client:
            return await client.call_tool(tool_name, payload)

    result = await asyncio.wait_for(call(), timeout=max(1.0, float(config.timeout_seconds)))
    return _stringify_mcp_result(result)


def _run_async(coro) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("MCP tool execution requires a synchronous worker context.")


def _stringify_mcp_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
            else:
                parts.append(str(item))
        if parts:
            return "\n".join(parts)
    if content is not None:
        return str(content)
    try:
        return json.dumps(result, indent=2, default=str)
    except TypeError:
        return str(result)
