"""Pure-ASGI middleware: request id, access log, metrics, security headers, safe 500s."""

import json
import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import reset_request_id, resolve_request_id, set_request_id
from app.observability.metrics import metrics

access_logger = logging.getLogger("pathforge.access")
error_logger = logging.getLogger("pathforge.error")

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
_API_CSP = "default-src 'none'; frame-ancestors 'none'"


async def _json_response(send: Send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str = "/api", max_body_bytes: int = 6_000_000):
        self.app = app
        self._max_body = max_body_bytes
        self._docs_paths = (f"{api_prefix}/docs", f"{api_prefix}/openapi.json", "/docs", "/redoc")

    def _headers_for(self, path: str, request_id: str) -> dict[str, str]:
        headers = {**_BASE_HEADERS, "X-Request-ID": request_id}
        if not path.startswith(self._docs_paths):  # Swagger UI needs inline scripts/styles
            headers["Content-Security-Policy"] = _API_CSP
        return headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw = dict(scope.get("headers") or [])
        request_id = resolve_request_id(raw.get(b"x-request-id", b"").decode("latin-1") or None)
        ctx_token = set_request_id(request_id)
        path = scope.get("path", "")
        extra = self._headers_for(path, request_id)
        started = time.perf_counter()
        status = 500
        response_started = False
        metrics.inc_in_flight()

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                headers = MutableHeaders(scope=message)
                for key, value in extra.items():
                    headers[key] = value
            await send(message)

        try:
            declared = raw.get(b"content-length", b"")
            if declared.isdigit() and int(declared) > self._max_body:
                await _json_response(send_wrapper, 413, {"detail": "Request body too large", "request_id": request_id})
                return
            await self.app(scope, receive, send_wrapper)
        except Exception:  # last line of defence: log with traceback, answer with a generic 500
            error_logger.exception("Unhandled error while handling %s %s", scope.get("method"), path)
            status = 500
            if not response_started:
                await _json_response(send_wrapper, 500, {"detail": "Internal server error", "request_id": request_id})
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", None) or "unmatched"  # template, never the raw path
            method = scope.get("method", "-")
            metrics.dec_in_flight()
            metrics.observe_request(method, route, status, elapsed)
            access_logger.info("%s %s -> %d (%.1f ms)", method, route, status, elapsed * 1000)
            reset_request_id(ctx_token)
