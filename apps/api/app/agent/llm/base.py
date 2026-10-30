"""
Abstraction the orchestrator depends on instead of any specific LLM
vendor. `plan()` decides which tools (if any) to call for a user
request; `synthesize()` turns tool results into a final answer. Swapping
DemoLLMProvider for RealLLMProvider (or a future OpenAI/etc. provider)
never touches orchestrator.py.

Both methods take the full AgentState (not just the raw request string)
so a provider can use target_role/conversation_context/identified_skills
when those are populated — fields that exist now for later phases to
fill in, per the Phase 4 brief's "keep state extensible."
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from app.agent.mcp_client import MCPToolDefinition
from app.agent.state import AgentState

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


class ToolCallPlanItem(BaseModel):
    tool_name: str
    arguments: dict
    reason: str = ""


class LLMProvider(ABC):
    @abstractmethod
    async def plan(
        self, state: AgentState, available_tools: list[MCPToolDefinition], max_tool_calls: int
    ) -> list[ToolCallPlanItem]:
        """Decide which tools (0 to max_tool_calls) are worth calling for
        this request. Must NOT default to calling every available tool —
        selection should reflect the request's actual intent."""
        ...

    @abstractmethod
    async def synthesize(self, state: AgentState) -> str:
        """Turn state.tool_calls (possibly empty, possibly
        partially-failed) into a final natural-language answer."""
        ...

    @abstractmethod
    async def generate_structured(self, system: str, user: str, schema: type[_SchemaT]) -> _SchemaT:
        """General-purpose structured generation: given a system prompt,
        a user prompt, and a Pydantic schema, return a validated instance
        of that schema. Used by capabilities beyond agent tool-planning
        — e.g. Phase 6's resume extraction — so they reuse this same
        provider abstraction rather than a second, parallel one.

        Implementations must validate their output against `schema`
        before returning; a response that doesn't validate is a
        malformed-response error, never silently passed through."""
        ...
