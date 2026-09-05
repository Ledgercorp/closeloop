from __future__ import annotations

import os

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from .lifecycle import ResolutionService
from .mcp_server import create_mcp_server


def _csv_environment(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _transport_security() -> TransportSecuritySettings:
    allowed_hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "testserver"]
    allowed_origins = ["http://127.0.0.1:*", "http://localhost:*"]

    vercel_host = os.getenv("VERCEL_URL", "").strip()
    if vercel_host:
        allowed_hosts.append(vercel_host)
        allowed_origins.append(f"https://{vercel_host}")

    allowed_hosts.extend(_csv_environment("CLOSELOOP_ALLOWED_HOSTS"))
    allowed_origins.extend(_csv_environment("CLOSELOOP_ALLOWED_ORIGINS"))
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_app(service: ResolutionService | None = None) -> FastAPI:
    mcp_server = create_mcp_server(service)
    mcp_http_app = mcp_server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(),
    )
    app = FastAPI(
        title="CloseLoop",
        version="0.2.0",
        lifespan=mcp_http_app.router.lifespan_context,
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "CloseLoop",
            "status": "ok",
            "message": "CloseLoop verification service is live.",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    app.router.routes.extend(mcp_http_app.routes)
    app.state.mcp_server = mcp_server
    return app
