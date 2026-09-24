# Alexa+-facing MCP server

`src/closeloop/mcp_server.py` mounts the authenticated self-hosted MCP server at `/mcp` in the FastAPI app. The seven tools are:

- `start_resolution` — create an owner-scoped cancellation and return confirmation requirements.
- `confirm_resolution_action` — execute only after a trusted, signed, short-lived action-bound confirmation.
- `get_resolution_status` — retrieve an authoritative resolution for a later-session question.
- `get_resolution_evidence` — inspect current and historical claims, read-backs, and verification results.
- `list_open_resolutions` — list unresolved work only.
- `list_recent_resolutions` — list bounded recent terminal history for the authenticated owner.
- `recheck_resolution` — perform a bounded independent read-back without repeating the action.

Schemas reject undeclared fields. There is no agent-controlled verdict/status operation. `PASS`, `FAIL`, and `INCONCLUSIVE` come only from the deterministic cancellation verifier; consumer states are Verified, Not completed, and Awaiting proof. `AWAITING_PROOF` remains open with a bounded check count and schedule metadata. Verified and Not completed are immutable.

Ownership is derived from the validated bearer token, never a tool argument. Confirmation binds owner, resolution, action digest, issuer, audience, issue time, expiry, and single-use identifier. Missing production confirmation authority denies all confirmations. SQL and optional DynamoDB repositories persist the same versioned record contract and condition writes against owner/state/version/history.

The local public demo simulates a later session using a second service instance over a temporary SQLite database. DynamoDB is Moto-tested only; Alexa+ account/device rendering and live AWS are not verified. No EventBridge, Lambda, or SQS scheduler is implemented.
