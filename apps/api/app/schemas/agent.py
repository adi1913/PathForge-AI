from typing import Literal

from pydantic import BaseModel, Field

from app.agent.state import AgentState


class AgentRunRequest(BaseModel):
    user_request: str = Field(min_length=1, max_length=2000)
    user_id: str | None = None
    target_role: str | None = None


class ToolUsedSummary(BaseModel):
    tool_name: str
    server_name: str
    success: bool
    reason: str = ""


class AgentResponse(BaseModel):
    """The only thing the API returns — never AgentState directly.
    Internal fields (raw tool arguments, full result payloads,
    conversation_context) stay server-side; this is the trimmed,
    user-facing contract."""

    answer: str
    sources: list[dict] = Field(default_factory=list)
    tools_used: list[ToolUsedSummary] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    follow_up_questions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    status: str = "completed"


def build_agent_response(state: AgentState) -> AgentResponse:
    tools_used = [
        ToolUsedSummary(
            tool_name=call.tool_name,
            server_name=call.server_name,
            success=bool(call.success),
            reason=call.reason,
        )
        for call in state.tool_calls
    ]

    sources = []
    for call in state.tool_calls:
        if call.success and call.result_summary:
            sources.append(
                {
                    "tool": call.tool_name,
                    "server": call.server_name,
                    "data": call.result_summary.get("data"),
                }
            )

    successes = sum(1 for c in state.tool_calls if c.success)
    if state.status.value == "failed" or not state.tool_calls:
        confidence: Literal["low", "medium", "high"] = "low"
    elif successes == len(state.tool_calls):
        confidence = "high"
    else:
        confidence = "medium"

    follow_ups: list[str] = []
    if not state.tool_calls:
        follow_ups.append("Could you say more about what you're trying to accomplish?")
    elif any(not c.success for c in state.tool_calls):
        follow_ups.append("Want me to try a different approach for the part that failed?")

    return AgentResponse(
        answer=state.final_response or "No response was generated.",
        sources=sources,
        tools_used=tools_used,
        confidence=confidence,
        follow_up_questions=follow_ups,
        errors=state.errors,
        status=state.status.value,
    )
