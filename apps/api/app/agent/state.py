from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallRecord(BaseModel):
    """Everything recorded about one tool call — mirrors the columns of
    the Phase 2 MCPToolLog model closely on purpose, so persisting one of
    these is a near-direct mapping (see orchestrator.py's _log_tool_call)."""

    server_name: str
    tool_name: str
    arguments: dict
    reason: str = ""  # why the planner chose this tool — for explainability
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    success: bool | None = None
    result_summary: dict | None = None  # bounded — never a raw unbounded dump
    error: str | None = None


class AgentState(BaseModel):
    """Explicit, typed state threaded through the orchestrator. Every
    later phase (RAG retrieval, skill gap analysis, roadmap generation)
    extends this rather than replacing it — fields for those are already
    present (identified_skills, gathered_evidence, target_role) even
    though nothing populates them meaningfully yet in Phase 4."""

    user_id: str | None = None
    user_request: str
    conversation_context: list[str] = Field(default_factory=list)
    target_role: str | None = None
    identified_skills: list[str] = Field(default_factory=list)
    gathered_evidence: list[dict] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    final_response: str | None = None
    status: AgentStatus = AgentStatus.PENDING
    run_id: str = Field(default_factory=lambda: uuid4().hex)
