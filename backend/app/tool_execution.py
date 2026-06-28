from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Mapping
from typing import Any

from .config import AppSettings
from .healthcare import HealthcareUserContext


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive for event-loop hosts
            error["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["error"]
    return result.get("value")


def _content_to_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    content = getattr(result, "content", None)
    if content is None and isinstance(result, Mapping):
        content = result.get("content")
    if content is None and isinstance(result, list):
        content = result
    if content is None:
        return json.dumps(result, default=str)

    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, Mapping):
            text = item.get("text")
        if text is None:
            text = str(item)
        parts.append(str(text))
    return "\n".join(parts)


class McpToolClient:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def call_project_tool(self, tool_name: str, payload: dict[str, Any]) -> str:
        return str(_run_async(self._call_project_tool(tool_name, payload)))

    async def _call_project_tool(self, tool_name: str, payload: dict[str, Any]) -> str:
        try:
            from fastmcp import Client
        except Exception as exc:  # pragma: no cover - depends on optional MCP install
            raise RuntimeError("fastmcp is not installed in the backend environment") from exc

        timeout = max(1, int(self.settings.mcp_tool_timeout_seconds or 30))
        args = {
            "project_id": self.settings.mcp_project_id,
            "payload": payload,
        }
        async with Client(self.settings.mcp_server_url) as client:
            return await asyncio.wait_for(
                self._call_tool_and_extract_text(client, tool_name, args),
                timeout=timeout,
            )

    @staticmethod
    async def _call_tool_and_extract_text(client: Any, mcp_tool_name: str, args: dict[str, Any]) -> str:
        result = await client.call_tool(mcp_tool_name, args)
        return _content_to_text(result)


class ToolExecutionRouter:
    def __init__(self, settings: AppSettings | None, user: HealthcareUserContext | None = None):
        self.settings = settings
        self.user = user
        self._client = McpToolClient(settings) if settings is not None else None

    def run(
        self,
        tool_name: str,
        query: str,
        local_run: Callable[[str], str],
        *,
        extra_payload: dict[str, Any] | None = None,
    ) -> str:
        if not self._mcp_enabled():
            return local_run(query)

        payload = {
            "query": query,
            "user_context": self._user_payload(),
            "extra": extra_payload or {},
        }
        try:
            assert self._client is not None
            return self._client.call_project_tool(tool_name, payload)
        except Exception as exc:
            if self.settings and self.settings.mcp_tool_fallback_to_local:
                return local_run(query)
            return f"Tool {tool_name} failed via MCP: {type(exc).__name__}: {exc}"

    def _mcp_enabled(self) -> bool:
        if self.settings is None:
            return False
        return str(self.settings.tool_execution_mode or "local").strip().lower() == "mcp"

    def _user_payload(self) -> dict[str, Any]:
        if self.user is None:
            return {}
        return {
            "user_id": self.user.user_id,
            "roles": list(self.user.roles),
            "departments": list(self.user.departments),
        }
