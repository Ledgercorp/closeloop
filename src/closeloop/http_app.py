from __future__ import annotations

import os

from fastapi import FastAPI, Request
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings

from .auth import auth_configuration_from_environment
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


def create_app(
    service: ResolutionService | None = None,
    auth_settings: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    if auth_settings is None and token_verifier is None:
        auth_settings, token_verifier = auth_configuration_from_environment()
    if auth_settings is None or token_verifier is None:
        raise ValueError("auth_settings and token_verifier must be configured together")

    mcp_server = create_mcp_server(
        service,
        auth_settings=auth_settings,
        token_verifier=token_verifier,
    )
    mcp_http_app = mcp_server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(),
    )
    app = FastAPI(
        title="CloseLoop",
        version="0.5.0",
        lifespan=mcp_http_app.router.lifespan_context,
    )

    @app.middleware("http")
    async def alexa_unauthenticated_discovery(request: Request, call_next):
        response = await call_next(request)
        if (
            request.url.path.rstrip("/") == "/mcp"
            and response.status_code == 401
            and "www-authenticate" in response.headers
        ):
            del response.headers["www-authenticate"]
        return response

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

    @app.get("/.well-known/oauth-protected-resource")
    def alexa_protected_resource_metadata() -> dict[str, object]:
        """Publish the root metadata alias documented by the Alexa+ MCP Toolkit."""

        return {
            "resource": str(auth_settings.resource_server_url),
            "authorization_servers": [str(auth_settings.issuer_url).rstrip("/")],
            "scopes_supported": list(auth_settings.required_scopes or []),
            "bearer_methods_supported": ["header"],
        }

    # Mount the complete MCP ASGI app so its authentication middleware remains
    # in the request path; copying only its routes would discard that boundary.
    app.mount("/", mcp_http_app)
    app.state.mcp_server = mcp_server
    return app
