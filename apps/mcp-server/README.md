# MCP Server

The Alexa+-facing service is implemented in `src/closeloop/mcp_server.py` and mounted by
the Vercel-compatible FastAPI application at `/mcp`.

It exposes exactly:

- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

The transport is stateless Streamable HTTP and negotiates MCP `2025-11-25` and `2025-03-26`
through the official SDK. Consequential execution occurs only in
`confirm_resolution_action` after `confirmed=true`. Unexpected input fields are rejected,
so callers cannot smuggle a verdict or terminal status into an action call.

Resolution state is durable through SQL or an optional Amazon DynamoDB repository. Local
development uses file-backed SQLite; a shared PostgreSQL URL or explicit DynamoDB table supports
serverless execution. DynamoDB uses owner/resolution composite keys, strongly consistent reads,
and version/state-checked conditional writes. Both repositories serialize competing instances and
cannot modify an existing terminal record.

Every MCP request requires a validated bearer token with the `closeloop:resolutions` scope.
Ownership is a hash of the validated issuer and subject; it is never an MCP argument. All reads,
confirmation, evidence fetches, and open-resolution lists are scoped to that owner. CloseLoop is
only a resource server in this milestone and does not implement token issuance, authorization
codes, refresh tokens, or PKCE. It publishes both the SDK path-suffixed protected-resource metadata
endpoint and the root alias documented by Alexa+. Unauthenticated `/mcp` discovery returns 401
without a challenge header; insufficient-scope 403 behavior remains unchanged.

Four lifecycle/detail tools link to a minimal `ui://closeloop/proof-card.html` MCP Apps resource.
The read-only card consumes structured tool results and displays task, execution, verification,
evidence summary, and Verified / Not completed / Awaiting proof. It has a meaningful text fallback
and a pinned CDN dependency on the official MCP Apps client. Its resource contract was validated
with MCP Inspector, but it was not rendered by the unavailable Alexa+ Local Inspector.

The provider remains a labeled demo simulation. The DynamoDB repository was validated with Moto,
not a live AWS account. Live Alexa+ onboarding, AWS orchestration, and real provider execution
remain later work. The deterministic verifier remains the sole verdict producer.
