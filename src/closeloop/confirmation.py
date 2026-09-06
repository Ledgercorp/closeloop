from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import jwt


CONFIRMATION_CONTRACT_VERSION = "closeloop.confirmation/v1"
CONFIRMATION_ACTION = "cancel_subscription"
CONFIRMATION_EXECUTION_ENVIRONMENT = "demo_simulation"
MAX_ATTESTATION_LENGTH = 4096
MAX_ATTESTATION_ID_LENGTH = 128
MAX_ATTESTATION_LIFETIME_SECONDS = 300
MAX_CONFIRMATION_AGE_SECONDS = 120
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


class ConfirmationAttestationError(ValueError):
    """A trusted confirmation attestation could not be established."""


@dataclass(frozen=True)
class ExpectedConfirmation:
    principal_id: str
    resolution_id: str
    action: str
    action_digest: str


@dataclass(frozen=True)
class VerifiedConfirmationAttestation:
    contract_version: str
    issuer: str
    attestation_id: str
    issued_at: datetime
    expires_at: datetime
    action_digest: str
    token_sha256: str


class ConfirmationAttestationVerifier(Protocol):
    def verify(
        self,
        attestation: str,
        expected: ExpectedConfirmation,
        *,
        now: datetime,
    ) -> VerifiedConfirmationAttestation: ...


def confirmation_action_digest(
    *,
    principal_id: str,
    resolution_id: str,
    intent: str,
    provider_mode: str,
) -> str:
    """Hash a domain-separated canonical description of the exact action."""

    payload = {
        "action": CONFIRMATION_ACTION,
        "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
        "execution_environment": CONFIRMATION_EXECUTION_ENVIRONMENT,
        "intent": intent,
        "principal_id": principal_id,
        "provider_mode": provider_mode,
        "resolution_id": resolution_id,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"closeloop-action-digest-v1\0" + encoded).hexdigest()


class DenyAllConfirmationAttestationVerifier:
    """Production-safe fallback when no trusted confirmation authority is configured."""

    def verify(
        self,
        attestation: str,
        expected: ExpectedConfirmation,
        *,
        now: datetime,
    ) -> VerifiedConfirmationAttestation:
        del attestation, expected, now
        raise ConfirmationAttestationError("trusted confirmation is unavailable")


class HmacJwtConfirmationAttestationVerifier:
    """Verify compact attestations issued by a separately trusted authorization boundary."""

    def __init__(self, *, secret: str, issuer: str, audience: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("confirmation secret must contain at least 32 bytes")
        if not issuer.strip() or not audience.strip():
            raise ValueError("confirmation issuer and audience are required")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def verify(
        self,
        attestation: str,
        expected: ExpectedConfirmation,
        *,
        now: datetime,
    ) -> VerifiedConfirmationAttestation:
        try:
            if not isinstance(attestation, str) or not attestation.strip():
                raise TypeError
            if len(attestation.encode("utf-8")) > MAX_ATTESTATION_LENGTH:
                raise ValueError
            claims = jwt.decode(
                attestation,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "confirmation_contract",
                        "sub",
                        "resolution_id",
                        "action",
                        "action_digest",
                        "confirmed",
                        "iat",
                        "exp",
                        "jti",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            string_claims = {
                key: claims.get(key)
                for key in (
                    "iss",
                    "aud",
                    "confirmation_contract",
                    "sub",
                    "resolution_id",
                    "action",
                    "action_digest",
                    "jti",
                )
            }
            if any(type(value) is not str for value in string_claims.values()):
                raise TypeError
            if claims.get("confirmed") is not True:
                raise ValueError
            issued_at = claims.get("iat")
            expires_at = claims.get("exp")
            if type(issued_at) is not int or type(expires_at) is not int:
                raise TypeError
            now_epoch = int(_utc(now).timestamp())
            if issued_at > now_epoch:
                raise ValueError
            if expires_at <= now_epoch or expires_at <= issued_at:
                raise ValueError
            if expires_at - issued_at > MAX_ATTESTATION_LIFETIME_SECONDS:
                raise ValueError
            if now_epoch - issued_at > MAX_CONFIRMATION_AGE_SECONDS:
                raise ValueError
            attestation_id = string_claims["jti"]
            action_digest = string_claims["action_digest"]
            if not attestation_id or len(attestation_id) > MAX_ATTESTATION_ID_LENGTH:
                raise ValueError
            if _HEX_DIGEST.fullmatch(action_digest) is None:
                raise ValueError
            if (
                string_claims["iss"] != self._issuer
                or string_claims["aud"] != self._audience
                or string_claims["confirmation_contract"]
                != CONFIRMATION_CONTRACT_VERSION
                or string_claims["sub"] != expected.principal_id
                or string_claims["resolution_id"] != expected.resolution_id
                or string_claims["action"] != expected.action
                or action_digest != expected.action_digest
            ):
                raise ValueError
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError) as exc:
            raise ConfirmationAttestationError(
                "trusted confirmation attestation was rejected"
            ) from exc

        return VerifiedConfirmationAttestation(
            contract_version=CONFIRMATION_CONTRACT_VERSION,
            issuer=self._issuer,
            attestation_id=attestation_id,
            issued_at=datetime.fromtimestamp(issued_at, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
            action_digest=action_digest,
            token_sha256=hashlib.sha256(attestation.encode("utf-8")).hexdigest(),
        )


def confirmation_attestation_verifier_from_environment() -> ConfirmationAttestationVerifier:
    secret = os.getenv("CLOSELOOP_CONFIRMATION_SECRET", "")
    issuer = os.getenv("CLOSELOOP_CONFIRMATION_ISSUER", "")
    audience = os.getenv("CLOSELOOP_CONFIRMATION_AUDIENCE", "")
    if not secret or not issuer or not audience:
        return DenyAllConfirmationAttestationVerifier()
    try:
        return HmacJwtConfirmationAttestationVerifier(
            secret=secret,
            issuer=issuer,
            audience=audience,
        )
    except ValueError:
        return DenyAllConfirmationAttestationVerifier()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
