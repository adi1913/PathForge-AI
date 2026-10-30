# Build from the REPOSITORY ROOT:  docker build -f apps/api/Dockerfile -t pathforge-api .
# The image mirrors the repo layout (/srv/pathforge/apps/api + /srv/pathforge/mcp-servers) because the agent
# locates the MCP servers relative to app/agent/mcp_config.py (see that file); the servers run as stdio subprocesses.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/pathforge/apps/api

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/ /srv/pathforge/apps/api/
COPY mcp-servers/ /srv/pathforge/mcp-servers/

RUN useradd --system --create-home --uid 10001 pathforge \
    && mkdir -p /srv/pathforge/data \
    && chown -R pathforge:pathforge /srv/pathforge \
    && chmod +x docker-entrypoint.sh
USER pathforge

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=4).status == 200 else 1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
