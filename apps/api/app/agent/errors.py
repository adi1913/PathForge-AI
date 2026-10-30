"""
Error types raised by the agent orchestrator and MCP client layer. Kept
separate from mcp-servers/common/errors.py deliberately — those are for
*inside* an MCP server's tool implementations; these are for the FastAPI
side that consumes MCP servers as a client. Never share exception
classes across that boundary.
"""


class AgentError(Exception):
    """Base class for all agent-layer errors."""

    def __init__(self, message: str, *, code: str = "agent_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class MCPConnectionError(AgentError):
    """An MCP server failed to start or the connection to it was lost."""

    def __init__(self, message: str):
        super().__init__(message, code="mcp_connection_error")


class ToolNotFoundError(AgentError):
    """The agent (or LLM plan) referenced a tool name no connected MCP
    server actually exposes."""

    def __init__(self, tool_name: str):
        super().__init__(f"No connected MCP server exposes a tool named '{tool_name}'", code="tool_not_found")
        self.tool_name = tool_name


class ToolExecutionError(AgentError):
    """A tool was found and called, but the call itself failed (MCP-level
    error result, or the call raised)."""

    def __init__(self, message: str):
        super().__init__(message, code="tool_execution_error")


class ToolTimeoutError(AgentError):
    def __init__(self, tool_name: str, timeout_seconds: float):
        super().__init__(f"Tool '{tool_name}' timed out after {timeout_seconds}s", code="tool_timeout")


class LLMUnavailableError(AgentError):
    """DEMO_MODE=false and no real LLM provider is configured."""

    def __init__(self, message: str):
        super().__init__(message, code="llm_unavailable")


class LLMTimeoutError(AgentError):
    def __init__(self, message: str):
        super().__init__(message, code="llm_timeout")


class MalformedLLMResponseError(AgentError):
    def __init__(self, message: str):
        super().__init__(message, code="malformed_llm_response")
