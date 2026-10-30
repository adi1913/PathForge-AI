"""
The only place in apps/api that speaks the MCP protocol. The agent
orchestrator (and everything else) calls tools through this manager —
never by importing mcp-servers/* implementation code directly. That
boundary is the whole point of using MCP at all.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import types as mcp_types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.agent.errors import MCPConnectionError, ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from app.agent.mcp_config import MCPServerConfig, default_server_configs

logger = logging.getLogger("pathforge.agent.mcp_client")

# Hard ceiling on how much of a tool's result we keep in memory / logs,
# independent of whatever bounding the MCP server itself already applies
# — defense in depth against one misbehaving server.
MAX_RESULT_BYTES = 20_000


@dataclass
class MCPToolDefinition:
    server_name: str
    tool_name: str
    description: str
    input_schema: dict


@dataclass
class _ConnectedServer:
    config: MCPServerConfig
    session: ClientSession
    tools: list[MCPToolDefinition] = field(default_factory=list)


class MCPClientManager:
    """Owns the connections to every configured MCP server for the
    lifetime of the app (opened once at FastAPI startup, closed at
    shutdown — see app/main.py's lifespan). Use as an async context
    manager, or call connect_all()/close() directly."""

    def __init__(self, configs: list[MCPServerConfig] | None = None):
        self._configs = configs if configs is not None else default_server_configs()
        self._servers: dict[str, _ConnectedServer] = {}
        self._tool_index: dict[str, _ConnectedServer] = {}  # tool_name -> owning server
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "MCPClientManager":
        await self.connect_all()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def connect_all(self) -> None:
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for config in self._configs:
            try:
                await self._connect_one(config)
            except Exception as exc:  # noqa: BLE001 - one bad server must not take down the others
                logger.warning("Failed to connect to MCP server '%s': %s", config.name, exc)
                # Deliberately do not re-raise here: a server that fails to
                # start (e.g. missing DEMO_MODE dependency, port issue)
                # should not crash the whole app — its tools are simply
                # unavailable, surfaced as ToolNotFoundError when referenced.

    async def _connect_one(self, config: MCPServerConfig) -> None:
        params = StdioServerParameters(command=config.command, args=config.args, env=config.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=config.timeout_seconds)

        list_result = await asyncio.wait_for(session.list_tools(), timeout=config.timeout_seconds)
        connected = _ConnectedServer(config=config, session=session)
        for tool in list_result.tools:
            definition = MCPToolDefinition(
                server_name=config.name,
                tool_name=tool.name,
                description=tool.description or "",
                input_schema=tool.input_schema,
            )
            connected.tools.append(definition)
            self._tool_index[tool.name] = connected
        self._servers[config.name] = connected
        logger.info("Connected to MCP server '%s' (%d tools)", config.name, len(connected.tools))

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._servers.clear()
        self._tool_index.clear()

    def list_tool_definitions(self) -> list[MCPToolDefinition]:
        """The dynamic tool catalog the agent plans against. Never
        hardcoded — comes from whatever list_tools() actually returned at
        connect time, from the servers that actually connected."""
        return [tool for server in self._servers.values() for tool in server.tools]

    def connected_server_names(self) -> list[str]:
        return list(self._servers.keys())

    async def call_tool(self, tool_name: str, arguments: dict) -> mcp_types.CallToolResult:
        connected = self._tool_index.get(tool_name)
        if connected is None:
            raise ToolNotFoundError(tool_name)

        try:
            result = await asyncio.wait_for(
                connected.session.call_tool(tool_name, arguments),
                timeout=connected.config.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ToolTimeoutError(tool_name, connected.config.timeout_seconds) from exc
        except Exception as exc:
            raise MCPConnectionError(
                f"Connection to MCP server '{connected.config.name}' failed while calling '{tool_name}'"
            ) from exc

        if result.is_error:
            message = result.content[0].text if result.content else "Tool call failed"
            raise ToolExecutionError(message[:500])  # bounded — never an unbounded echo

        return result


def bounded_result_summary(result: mcp_types.CallToolResult) -> dict:
    """Converts a CallToolResult into something safe/small enough to keep
    in agent state and MCPToolLog — never the raw, potentially large
    structured_content verbatim."""
    content = result.structured_content or {}
    serialized = str(content)
    if len(serialized) > MAX_RESULT_BYTES:
        return {"truncated": True, "preview": serialized[:MAX_RESULT_BYTES]}
    return {"truncated": False, "data": content}
