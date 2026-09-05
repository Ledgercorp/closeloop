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

Milestone 2 storage is process-local and the provider is a labeled demo simulation. Durable
cross-instance state, remote authentication/PKCE, Alexa+ client setup, and real provider
execution remain later work. The deterministic verifier remains the sole verdict producer.
