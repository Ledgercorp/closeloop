from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from closeloop.confirmation import (
    CONFIRMATION_ACTION,
    CONFIRMATION_CONTRACT_VERSION,
    ExpectedConfirmation,
    HmacJwtConfirmationAttestationVerifier,
)


TEST_CONFIRMATION_SECRET = "test-confirmation-secret-that-is-at-least-thirty-two-bytes"
TEST_CONFIRMATION_ISSUER = "https://confirmation-authority.test"
TEST_CONFIRMATION_AUDIENCE = "https://closeloop.test/confirmation"


class TestConfirmationAttestationIssuer:
    """Deterministic test-only issuer; this module is never imported by production code."""

    def issue(
        self,
        status: dict[str, object],
        principal_id: str,
        *,
        now: datetime | None = None,
        lifetime_seconds: int = 60,
        overrides: dict[str, object] | None = None,
        secret: str = TEST_CONFIRMATION_SECRET,
        issuer: str = TEST_CONFIRMATION_ISSUER,
    ) -> str:
        issued = now or datetime.now(timezone.utc)
        claims: dict[str, object] = {
            "iss": issuer,
            "aud": TEST_CONFIRMATION_AUDIENCE,
            "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
            "sub": principal_id,
            "resolution_id": status["resolution_id"],
            "action": status["action"],
            "action_digest": status["action_digest"],
            "confirmed": True,
            "iat": int(issued.timestamp()),
            "exp": int((issued + timedelta(seconds=lifetime_seconds)).timestamp()),
            "jti": str(uuid4()),
        }
        claims.update(overrides or {})
        return jwt.encode(claims, secret, algorithm="HS256")


TEST_CONFIRMATION_ISSUER_INSTANCE = TestConfirmationAttestationIssuer()


def trusted_confirmation(
    status: dict[str, object],
    principal_id: str,
    **kwargs,
) -> str:
    return TEST_CONFIRMATION_ISSUER_INSTANCE.issue(status, principal_id, **kwargs)


def verified_test_confirmation(
    status: dict[str, object],
    principal_id: str,
    *,
    now: datetime,
):
    token = trusted_confirmation(status, principal_id, now=now)
    verifier = HmacJwtConfirmationAttestationVerifier(
        secret=TEST_CONFIRMATION_SECRET,
        issuer=TEST_CONFIRMATION_ISSUER,
        audience=TEST_CONFIRMATION_AUDIENCE,
    )
    return verifier.verify(
        token,
        ExpectedConfirmation(
            principal_id=principal_id,
            resolution_id=str(status["resolution_id"]),
            action=CONFIRMATION_ACTION,
            action_digest=str(status["action_digest"]),
        ),
        now=now,
    )
