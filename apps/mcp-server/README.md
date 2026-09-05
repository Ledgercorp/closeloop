# MCP Server

The Alexa+-facing service is implemented in `src/closeloop/mcp_server.py` and mounted by
the Vercel-compatible FastAPI application at `/mcp`.

It exposes exactly:

- `start_resolution`
- `confirm_resolution_action`
- `get_resolution_status`
- `get_resolution_evidence`
- `list_open_resolutions`

The transport is stateless Streamable HTTP and negotiates MCP `2025-11-25` (as well as
newer versions supported by the official SDK). Consequential execution occurs only in
`confirm_resolution_action` after `confirmed=true`. Unexpected input fields are rejected,
so callers cannot smuggle a verdict or terminal status into an action call.

Resolution state is durable through a SQL repository. Local development uses file-backed SQLite;
Vercel/serverless execution requires a shared PostgreSQL URL. Version-checked conditional updates
serialize competing instances, and repository updates cannot modify an existing terminal row.

Every MCP request requires a validated bearer token with the `closeloop:resolutions` scope.
Ownership is a hash of the validated issuer and subject; it is never an MCP argument. All reads,
confirmation, evidence fetches, and open-resolution lists are scoped to that owner. CloseLoop is
only a resource server in this milestone and does not implement token issuance or PKCE.

The provider remains a labeled demo simulation. Alexa+ client setup, AWS orchestration, and real
provider execution remain later work. The deterministic verifier remains the sole verdict
producer.
