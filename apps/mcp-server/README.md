# MCP Server — Next Milestone

This directory will contain the Alexa+-facing MCP server.

Requirements to validate before implementation:
- current Alexa+ supported MCP spec version
- Streamable HTTP transport
- remotely reachable endpoint
- Alexa-compatible auth / PKCE when authentication is enabled
- narrow, asynchronous tool surface

The deterministic verifier already exists in `src/closeloop` and must remain independent of action-agent self-reporting.
