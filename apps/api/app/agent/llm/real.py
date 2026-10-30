"""
Real (non-demo) LLM provider. Implemented against the Anthropic Messages
API directly over httpx — no `anthropic` SDK dependency, consistent with
how mcp-servers/*/providers/live.py talks to GitHub directly rather than
through a wrapper library.

NOT exercised against a live API in development/CI for this project so
far (no LLM_API_KEY configured in the reference environment) — see
docs/architecture.md "known limitations." The demo pipeline
(DemoLLMProvider) is what's actually verified end to end.

Only `LLM_PROVIDER=anthropic` is implemented concretely; `openai` raises
NotImplementedError with a clear message rather than pretending to work
— the point of the LLMProvider abstraction is that adding a real OpenAI
implementation later doesn't touch the orchestrator, not that every
vendor is implemented today.
"""

import json

import httpx
from pydantic import BaseModel

from app.agent.errors import LLMTimeoutError, LLMUnavailableError, MalformedLLMResponseError
from app.agent.llm.base import LLMProvider, ToolCallPlanItem
from app.agent.mcp_client import MCPToolDefinition
from app.agent.state import AgentState
from app.core.config import Settings, get_settings

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class _PlanToolUse(BaseModel):
    name: str
    input: dict


class RealLLMProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        if self._settings.LLM_PROVIDER == "mock":
            raise LLMUnavailableError(
                "LLM_PROVIDER is set to 'mock' but DEMO_MODE=false — set LLM_PROVIDER=anthropic "
                "and LLM_API_KEY, or set DEMO_MODE=true to use the demo provider instead."
            )
        if self._settings.LLM_PROVIDER != "anthropic":
            raise NotImplementedError(
                f"LLM_PROVIDER={self._settings.LLM_PROVIDER!r} has no RealLLMProvider implementation yet. "
                "Only 'anthropic' is implemented; add a branch here to support another vendor without "
                "changing the orchestrator or the LLMProvider interface."
            )
        if not self._settings.LLM_API_KEY:
            raise LLMUnavailableError(
                "LLM_PROVIDER=anthropic but LLM_API_KEY is not set. Configure LLM_API_KEY, "
                "or set DEMO_MODE=true to use the demo provider instead."
            )

    def _headers(self) -> dict[str, str]:
        # The API key goes only in this header, on this one outgoing
        # request — never logged, never included in any exception message
        # raised by this class.
        return {
            "x-api-key": self._settings.LLM_API_KEY,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def _post(self, body: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(_ANTHROPIC_API_URL, headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Anthropic API request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Anthropic API request failed: network error ({type(exc).__name__})") from exc

        if response.status_code >= 400:
            # Deliberately not including response.text: could echo back
            # request content in some error modes. Status code is enough
            # to act on (auth vs rate limit vs bad request).
            raise LLMUnavailableError(f"Anthropic API returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise MalformedLLMResponseError("Anthropic API returned a non-JSON response") from exc

    @staticmethod
    def _tool_schema(tools: list[MCPToolDefinition]) -> list[dict]:
        return [{"name": t.tool_name, "description": t.description, "input_schema": t.input_schema} for t in tools]

    async def plan(
        self, state: AgentState, available_tools: list[MCPToolDefinition], max_tool_calls: int
    ) -> list[ToolCallPlanItem]:
        if not available_tools:
            return []

        body = {
            "model": self._settings.LLM_MODEL,
            "max_tokens": 1024,
            "system": (
                "You are the tool-selection stage of a career/learning agent. Given the user's request, "
                f"decide which of the available tools (if any) are worth calling — at most {max_tool_calls}. "
                "Do not call a tool unless it's actually relevant to the request. Call tools directly; do "
                "not respond with plain text."
            ),
            "messages": [{"role": "user", "content": state.user_request}],
            "tools": self._tool_schema(available_tools),
        }
        response = await self._post(body)

        plan: list[ToolCallPlanItem] = []
        for block in response.get("content", []):
            if block.get("type") == "tool_use":
                try:
                    tool_use = _PlanToolUse(name=block["name"], input=block.get("input", {}))
                except Exception as exc:
                    raise MalformedLLMResponseError("Anthropic response contained a malformed tool_use block") from exc
                plan.append(
                    ToolCallPlanItem(tool_name=tool_use.name, arguments=tool_use.input, reason="Selected by LLM")
                )
        return plan[:max_tool_calls]

    async def synthesize(self, state: AgentState) -> str:
        results_text = json.dumps(
            [
                {
                    "tool": call.tool_name,
                    "success": call.success,
                    "result": call.result_summary,
                    "error": call.error,
                }
                for call in state.tool_calls
            ],
            default=str,
        )
        body = {
            "model": self._settings.LLM_MODEL,
            "max_tokens": 1024,
            "system": (
                "You are the response-synthesis stage of a career/learning agent. Given the user's "
                "original request and the results of the tools that were called, write a concise, "
                "helpful natural-language answer. If a tool failed, acknowledge it briefly rather than "
                "pretending it succeeded."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": f"User request: {state.user_request}\n\nTool results (JSON): {results_text}",
                }
            ],
        }
        response = await self._post(body)
        text_blocks = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
        if not text_blocks:
            raise MalformedLLMResponseError("Anthropic response contained no text content to use as an answer")
        return "\n".join(text_blocks).strip()

    async def generate_structured(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Forces the model to respond via a single synthetic tool whose
        input_schema is the target Pydantic schema's JSON schema — the
        same reliable pattern used for tool-call planning above, just
        aimed at getting validated structured output instead of a tool
        selection. Validates with Pydantic; on a validation failure,
        makes exactly one repair attempt (telling the model what was
        wrong) before giving up — "repaired safely," not an unbounded
        retry loop."""
        return await self._generate_structured_attempt(system, user, schema, repair_note=None)

    async def _generate_structured_attempt(
        self, system: str, user: str, schema: type[BaseModel], repair_note: str | None
    ) -> BaseModel:
        tool_name = "emit_structured_output"
        body = {
            "model": self._settings.LLM_MODEL,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user if repair_note is None else f"{user}\n\n{repair_note}"}],
            "tools": [
                {
                    "name": tool_name,
                    "description": "Emit the extracted result as structured data matching the required schema.",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        response = await self._post(body)

        tool_use = next((b for b in response.get("content", []) if b.get("type") == "tool_use"), None)
        if tool_use is None:
            raise MalformedLLMResponseError("Anthropic response contained no structured tool_use block")

        try:
            return schema(**tool_use.get("input", {}))
        except Exception as exc:
            if repair_note is not None:
                # Already tried a repair once — don't loop forever.
                raise MalformedLLMResponseError(
                    f"Anthropic returned output that didn't match the required schema, twice: {exc}"
                ) from exc
            return await self._generate_structured_attempt(
                system,
                user,
                schema,
                repair_note=(
                    f"Your previous output did not match the required schema ({exc}). "
                    "Emit corrected output via the same tool, matching the schema exactly."
                ),
            )
