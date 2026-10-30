"""Readiness and metrics. /health (liveness) stays in health.py. Neither endpoint exposes secrets or user data."""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.observability.metrics import metrics

router = APIRouter()


@router.get("/health/ready")
def readiness(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """200 when the database answers; 503 otherwise. Vector store / MCP state is reported but does not gate readiness
    (the API still serves auth, roadmaps, applications etc. without them)."""
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 - a readiness probe must report, not crash, on any DB error
        database_ok = False
    mcp = getattr(request.app.state, "mcp_manager", None)
    body = {
        "status": "ready" if database_ok else "not_ready",
        "checks": {
            "database": database_ok,
            "vector_store": getattr(request.app.state, "vector_store", None) is not None,
            "mcp_servers_connected": len(mcp.connected_server_names()) if mcp is not None else 0,
        },
    }
    return JSONResponse(body, status_code=200 if database_ok else 503)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint(request: Request, settings: Settings = Depends(get_settings)) -> PlainTextResponse:
    if not settings.METRICS_ENABLED or (settings.ENVIRONMENT == "production" and not settings.METRICS_TOKEN):
        raise HTTPException(status_code=404, detail="Not found")
    if settings.METRICS_TOKEN:
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), settings.METRICS_TOKEN.encode()):
            raise HTTPException(
                status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"}
            )
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
