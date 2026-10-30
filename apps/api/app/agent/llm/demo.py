"""
Deterministic tool selection + templated synthesis, used whenever
DEMO_MODE=true (the default) or as a fallback with no LLM configured.
No API key, no network call to any LLM provider — just enough intent
matching to prove the full agent -> MCP -> tool -> response pipeline
works end to end. Real reasoning is RealLLMProvider's job (Phase 4,
implemented but requiring a configured API key to actually run).
"""

import re

from pydantic import BaseModel

from app.agent.errors import LLMUnavailableError
from app.agent.llm.base import LLMProvider, ToolCallPlanItem
from app.agent.mcp_client import MCPToolDefinition
from app.agent.state import AgentState

_GITHUB_KEYWORDS = {"github", "repo", "repos", "repository", "repositories", "project", "projects"}
_LEARNING_KEYWORDS = {"learn", "learning", "become", "career", "skill", "skills", "role", "roadmap", "study"}
_JOB_KEYWORDS = {"job", "jobs", "hiring", "position", "positions", "opening", "openings"}
_STOPWORDS = {
    "a",
    "an",
    "the",
    "to",
    "for",
    "of",
    "on",
    "in",
    "and",
    "or",
    "i",
    "my",
    "me",
    "want",
    "would",
    "like",
    "please",
    "find",
    "good",
    "some",
    "show",
    "help",
    "with",
    "what",
    "should",
    "how",
    "can",
    "do",
    "does",
    "is",
    "are",
    "you",
    "your",
}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9\-]*", text.lower()))


def _extract_query(user_request: str, drop: set[str]) -> str:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]*", user_request) if w.lower() not in drop | _STOPWORDS]
    query = " ".join(words).strip()
    return query or user_request.strip()


class DemoLLMProvider(LLMProvider):
    async def plan(
        self, state: AgentState, available_tools: list[MCPToolDefinition], max_tool_calls: int
    ) -> list[ToolCallPlanItem]:
        available_names = {t.tool_name for t in available_tools}
        tokens = _tokenize(state.user_request)
        plan: list[ToolCallPlanItem] = []

        if tokens & _GITHUB_KEYWORDS and "search_github_repositories" in available_names:
            query = _extract_query(state.user_request, _GITHUB_KEYWORDS)
            plan.append(
                ToolCallPlanItem(
                    tool_name="search_github_repositories",
                    arguments={"query": query, "max_results": 5},
                    reason="Request mentions GitHub/repositories — searching for relevant repos as evidence/examples.",
                )
            )

        if tokens & _LEARNING_KEYWORDS:
            role = state.target_role or _extract_query(state.user_request, _LEARNING_KEYWORDS)
            if "search_technology_requirements" in available_names:
                plan.append(
                    ToolCallPlanItem(
                        tool_name="search_technology_requirements",
                        arguments={"role": role},
                        reason=(
                            "Request is about learning/career goals — checking what the "
                            "target role actually requires."
                        ),
                    )
                )
            if "search_learning_resources" in available_names:
                plan.append(
                    ToolCallPlanItem(
                        tool_name="search_learning_resources",
                        arguments={"query": state.user_request, "max_results": 5},
                        reason="Finding learning resources relevant to the stated goal.",
                    )
                )

        if tokens & _JOB_KEYWORDS and "search_jobs" in available_names:
            role = state.target_role or _extract_query(state.user_request, _JOB_KEYWORDS)
            plan.append(
                ToolCallPlanItem(
                    tool_name="search_jobs",
                    arguments={"role": role},
                    reason="Request is about job listings for a role.",
                )
            )

        if not plan and "web_search" in available_names:
            plan.append(
                ToolCallPlanItem(
                    tool_name="web_search",
                    arguments={"query": state.user_request},
                    reason="No specific intent matched — falling back to a general web search.",
                )
            )

        return plan[:max_tool_calls]

    async def synthesize(self, state: AgentState) -> str:
        if not state.tool_calls:
            return (
                "I wasn't able to find a relevant tool for that request, and no results were gathered. "
                "Try rephrasing, or ask about GitHub projects, learning resources, job listings, or role requirements."
            )

        lines: list[str] = []
        any_success = False
        for call in state.tool_calls:
            if not call.success:
                lines.append(f"- {call.tool_name} failed: {call.error or 'unknown error'}")
                continue
            any_success = True
            data = (call.result_summary or {}).get("data", {})
            lines.append(f"- {call.tool_name}: {_summarize_result(call.tool_name, data)}")

        header = "Here's what I found:" if any_success else "I ran the relevant tools, but none of them succeeded:"
        return header + "\n" + "\n".join(lines)

    async def generate_structured(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        # Deliberately refuses rather than fabricating: demo mode's
        # resume extraction (Phase 6) and anything else that needs real
        # structured generation must use rule-based extraction instead,
        # never a demo LLM inventing plausible-looking JSON.
        raise LLMUnavailableError(
            "DemoLLMProvider does not perform structured generation — it would have to fabricate "
            "output. Use a rule-based extractor for DEMO_MODE, or configure a real LLM provider."
        )


def _summarize_result(tool_name: str, data: dict) -> str:
    if not data:
        return "no data returned"
    if "results" in data and isinstance(data["results"], list):
        count = len(data["results"])
        first = data["results"][0] if data["results"] else None
        first_desc = ""
        if isinstance(first, dict):
            first_desc = first.get("title") or first.get("name") or ""
        return f"{count} result(s) found" + (f", e.g. '{first_desc}'" if first_desc else "")
    if "requirements" in data and isinstance(data["requirements"], list):
        top = ", ".join(r.get("technology", "") for r in data["requirements"][:3])
        return f"top requirements: {top}" if top else "no requirements data"
    if "repository" in data:
        return f"details for {data['repository'].get('full_name', 'the repository')}"
    return "data returned"
