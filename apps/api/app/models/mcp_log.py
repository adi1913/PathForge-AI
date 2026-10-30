from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, utcnow
from app.models.enums import MCPToolStatus


class MCPToolLog(UUIDPKMixin, Base):
    """One row per MCP tool invocation. `input_metadata`/`output_metadata`
    must hold sanitized summaries only (e.g. arg keys and shapes, result
    counts) — the sanitization itself is enforced in the MCP client code
    added in Phase 3, not at the DB layer, but this model deliberately
    has no columns named anything like `token`/`api_key`/`secret` to make
    that misuse harder by omission."""

    __tablename__ = "mcp_tool_logs"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)  # correlates one agent run
    server_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    input_metadata: Mapped[dict | None] = mapped_column(JSON)
    output_metadata: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[MCPToolStatus] = mapped_column(Enum(MCPToolStatus, native_enum=False, length=20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User | None"] = relationship()
