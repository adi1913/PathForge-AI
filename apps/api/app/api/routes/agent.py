from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.agent.llm.factory import get_llm_provider
from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import AgentState
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.agent import AgentResponse, AgentRunRequest, build_agent_response
from app.security.deps import AuthUser, get_current_user

router = APIRouter()


@router.post("/agent/run", response_model=AgentResponse)
async def run_agent(
    payload: AgentRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthUser = Depends(get_current_user),
) -> AgentResponse:
    """Minimal endpoint to exercise the orchestrator end to end. Requires authentication; the request's ``user_id`` is
    optional and, when present, must be the authenticated user (it only attributes ``MCPToolLog`` rows)."""
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if mcp_manager is None:
        raise HTTPException(status_code=503, detail="MCP client is not initialized")

    try:
        llm_provider = get_llm_provider()
    except AgentError as exc:
        # DEMO_MODE=false with no LLM configured — a clear 503, not a 500
        # with a stack trace, and not a silent fallback to demo behavior.
        raise HTTPException(status_code=503, detail=exc.message) from exc

    settings = get_settings()
    orchestrator = AgentOrchestrator(
        mcp_manager=mcp_manager,
        llm_provider=llm_provider,
        db=db,
        max_tool_calls=settings.AGENT_MAX_TOOL_CALLS,
    )
    state = AgentState(
        user_id=auth.bind(payload.user_id),
        user_request=payload.user_request,
        target_role=payload.target_role,
    )
    state = await orchestrator.run(state)
    return build_agent_response(state)
