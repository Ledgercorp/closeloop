from __future__ import annotations

import hashlib
import os
from collections.abc import Callable

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings


REQUIRED_SCOPE = "closeloop:resolutions"


class AuthenticationRequiredError(ValueError):
    """Raised when no validated resource-owner identity is available."""


def principal_key(issuer: str, subject: str) -> str:
    """Create a non-PII ownership key scoped to an issuer and subject."""

    return hashlib.sha256(f"closeloop-owner-v1\0{issuer}\0{subject}".encode()).hexdigest()


def principal_from_authenticated_request() -> str:
    token = get_access_token()
    issuer = str((token.claims or {}).get("iss", "")) if token else ""
    subject = token.subject if token else None
    if not issuer or not subject:
        raise AuthenticationRequiredError("an authenticated principal is required")
    return principal_key(issuer, subject)


class HmacJwtTokenVerifier(TokenVerifier):
    """Validate externally issued, audience-bound HS256 access tokens.

    CloseLoop does not mint tokens. A shared secret and issuer are deployment
    configuration; missing or weak configuration fails closed.
    """

    def __init__(self, secret: str | None, issuer: str, audience: str) -> None:
        self._secret = secret if secret and len(secret.encode()) >= 32 else None
        self._issuer = issuer
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        if self._secret is None:
            return None
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None

        scopes_claim = claims.get("scope", "")
        scopes = scopes_claim.split() if isinstance(scopes_claim, str) else []
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "closeloop-client")),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self._audience,
            subject=subject,
            claims=claims,
        )


def auth_configuration_from_environment() -> tuple[AuthSettings, HmacJwtTokenVerifier]:
    vercel_host = os.getenv("VERCEL_URL", "").strip()
    default_resource = f"https://{vercel_host}/mcp" if vercel_host else "http://localhost:8000/mcp"
    issuer = os.getenv("CLOSELOOP_AUTH_ISSUER", "https://closeloop.local").rstrip("/")
    resource = os.getenv("CLOSELOOP_AUTH_AUDIENCE", default_resource)
    settings = AuthSettings(
        issuer_url=issuer,
        resource_server_url=resource,
        required_scopes=[REQUIRED_SCOPE],
    )
    verifier = HmacJwtTokenVerifier(
        secret=os.getenv("CLOSELOOP_AUTH_SECRET"),
        issuer=issuer,
        audience=resource,
    )
    return settings, verifier


PrincipalResolver = Callable[[], str]
