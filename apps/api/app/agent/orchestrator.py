"""
The Agent Orchestrator: Planning -> Tool Selection -> MCP Execution ->
Result Aggregation -> Response Generation, as a single bounded pass (no
autonomous loop yet — that's a later-phase concern, and the brief is
explicit that Phase 4 should NOT implement one).
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.agent.llm.base import LLMProvider
from app.agent.mcp_client import MCPClientManager, bounded_result_summary
from app.agent.state import AgentState, AgentStatus, ToolCallRecord
from app.models.enums import MCPToolStatus
from app.models.mcp_log import MCPToolLog

logger = logging.getLogger("pathforge.agent.orchestrator")

DEFAULT_MAX_TOOL_CALLS = 5


class AgentOrchestrator:
    def __init__(
        self,
        mcp_manager: MCPClientManager,
        llm_provider: LLMProvider,
        db: Session | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ):
        self._mcp_manager = mcp_manager
        self._llm_provider = llm_provider
        self._db = db
        self._max_tool_calls = max_tool_calls

    async def run(self, state: AgentState) -> AgentState:
        state.status = AgentStatus.RUNNING
        run_id = state.run_id or uuid.uuid4().hex
        state.run_id = run_id

        try:
            available_tools = self._mcp_manager.list_tool_definitions()

            # --- Planning / Tool Selection ---
            plan = await self._llm_provider.plan(state, available_tools, self._max_tool_calls)
            if len(plan) > self._max_tool_calls:
                state.errors.append(
                    f"LLM plan requested {len(plan)} tool calls; truncated to the configured "
                    f"maximum of {self._max_tool_calls}."
                )
                plan = plan[: self._max_tool_calls]

            # --- MCP Execution ---
            for item in plan:
                record = await self._execute_tool_call(item.tool_name, item.arguments, item.reason, run_id, state)
                state.tool_calls.append(record)
                if record.success and record.result_summary is not None:
                    state.tool_results.append(record.result_summary.get("data", {}))

            # --- Response Generation ---
            state.final_response = await self._llm_provider.synthesize(state)
            state.status = AgentStatus.COMPLETED

        except AgentError as exc:
            logger.warning("Agent run %s failed: %s", run_id, exc.message)
            state.errors.append(exc.message)
            state.status = AgentStatus.FAILED
            state.final_response = "I couldn't complete that request due to an internal error. Please try again."
        except Exception:
            logger.exception("Agent run %s failed with an unexpected error", run_id)
            state.errors.append("An unexpected error occurred while processing this request.")
            state.status = AgentStatus.FAILED
            state.final_response = "I couldn't complete that request due to an internal error. Please try again."

        return state

    async def _execute_tool_call(
        self, tool_name: str, arguments: dict, reason: str, run_id: str, state: AgentState
    ) -> ToolCallRecord:
        record = ToolCallRecord(
            server_name="",
            tool_name=tool_name,
            arguments=_bounded_arguments(arguments),
            reason=reason,
        )
        start = time.monotonic()
        try:
            result = await self._mcp_manager.call_tool(tool_name, arguments)
            record.success = True
            record.result_summary = bounded_result_summary(result)
            record.server_name = self._server_name_for(tool_name)
        except AgentError as exc:
            record.success = False
            record.error = exc.message
            record.server_name = self._server_name_for(tool_name) or "unknown"
        finally:
            record.completed_at = datetime.now(timezone.utc)
            record.duration_ms = int((time.monotonic() - start) * 1000)

        self._log_tool_call(run_id, state.user_id, record)
        return record

    def _server_name_for(self, tool_name: str) -> str:
        for tool in self._mcp_manager.list_tool_definitions():
            if tool.tool_name == tool_name:
                return tool.server_name
        return ""

    def _log_tool_call(self, run_id: str, user_id: str | None, record: ToolCallRecord) -> None:
        """Persists to the Phase 2 MCPToolLog table. Never stores raw
        arguments/results beyond what's already bounded in `record` —
        result_summary is already capped by bounded_result_summary, and
        arguments were already capped by _bounded_arguments."""
        if self._db is None:
            return
        try:
            self._db.add(
                MCPToolLog(
                    user_id=user_id,
                    run_id=run_id,
                    server_name=record.server_name or "unknown",
                    tool_name=record.tool_name,
                    input_metadata=record.arguments,
                    output_metadata=record.result_summary,
                    status=MCPToolStatus.SUCCESS if record.success else MCPToolStatus.ERROR,
                    latency_ms=record.duration_ms,
                    error_type=None if record.success else (record.error or "")[:150],
                )
            )
            self._db.commit()
        except Exception:
            logger.exception("Failed to persist MCPToolLog for run %s", run_id)
            self._db.rollback()


_MAX_ARG_STRING_LEN = 500


def _bounded_arguments(arguments: dict) -> dict:
    """Caps any individual string argument before it's stored (as agent
    state or an MCPToolLog row) — defense against a pathologically long
    user-supplied argument value bloating logs."""
    bounded = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > _MAX_ARG_STRING_LEN:
            bounded[key] = value[:_MAX_ARG_STRING_LEN] + "...(truncated)"
        else:
            bounded[key] = value
    return bounded
