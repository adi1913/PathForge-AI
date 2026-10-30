import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.mcp_client import MCPClientManager
from app.api.routes import (
    agent,
    applications,
    assessments,
    auth,
    github,
    health,
    job_descriptions,
    mentor,
    ops,
    rag,
    resume,
    roadmaps,
)
from app.core.config import get_settings
from app.observability.logging import configure_logging
from app.observability.middleware import ObservabilityMiddleware
from app.rag.vector_store.factory import get_vector_store
from app.security.deps import enforce_user_binding
from app.security.validation import validate_settings

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("pathforge.main")
for _warning in validate_settings(settings):  # raises for unsafe staging/production settings
    logger.warning("Insecure setting (allowed only for local/test): %s", _warning)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connects to every configured MCP server ONCE at startup (real
    stdio subprocesses + MCP protocol handshake + tool discovery — see
    app/agent/mcp_client.py), keeps those connections open for the life
    of the process, and closes them cleanly at shutdown. Per-request
    connect/disconnect would work but pays a subprocess-spawn cost on
    every single agent request for no benefit.

    Also opens the vector store ONCE here for the same reason — Qdrant's
    embedded local-mode client owns an on-disk storage handle that
    shouldn't be repeatedly opened/closed per request."""
    mcp_manager = MCPClientManager()
    await mcp_manager.connect_all()
    connected = mcp_manager.connected_server_names()
    tool_count = len(mcp_manager.list_tool_definitions())
    if connected:
        logger.info("MCP client connected to %s (%d tools total)", connected, tool_count)
    else:
        logger.warning("MCP client connected to no servers — agent tool calls will fail with ToolNotFoundError")
    app.state.mcp_manager = mcp_manager

    vector_store = get_vector_store()
    app.state.vector_store = vector_store

    try:
        yield
    finally:
        await mcp_manager.close()
        close = getattr(vector_store, "close", None)
        if close is not None:
            await close()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "PathForge AI backend: agent + MCP client, RAG, resume analysis, job description "
        "skill-gap analysis, roadmap generation, adaptive re-planning, job application tracking and "
        "GitHub repository skill evidence, assessments with persistent evidence, and a contextual mentor. "
        "Protected by bearer-token authentication (see /api/auth/login)."
    ),
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # bearer tokens travel in a header; no cookies are used
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
# Outermost: request id, access log, metrics, security headers, safe 500s (also covers CORS responses).
app.add_middleware(
    ObservabilityMiddleware, api_prefix=settings.API_V1_PREFIX, max_body_bytes=settings.MAX_REQUEST_BODY_BYTES
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Standard 422 shape, minus the echoed ``input``/``ctx`` (which could contain a submitted password)."""
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", "Invalid value"), "type": e.get("type", "value_error")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


# Public: liveness/readiness/metrics (metrics has its own token rule) and the auth endpoints themselves.
app.include_router(health.router, prefix=settings.API_V1_PREFIX, tags=["health"])
app.include_router(ops.router, prefix=settings.API_V1_PREFIX, tags=["health"])
app.include_router(auth.router, prefix=settings.API_V1_PREFIX, tags=["auth"])

# Everything else requires a valid token, and any user_id the caller supplies must be the token's user.
_protected = [Depends(enforce_user_binding)]
for _router, _tag in (
    (agent.router, "agent"),
    (rag.router, "rag"),
    (resume.router, "resume"),
    (job_descriptions.router, "job-descriptions"),
    (roadmaps.router, "roadmaps"),
    (applications.router, "applications"),
    (github.router, "github"),
    (assessments.router, "assessments"),
    (mentor.router, "mentor"),
):
    app.include_router(_router, prefix=settings.API_V1_PREFIX, tags=[_tag], dependencies=_protected)
