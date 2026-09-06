# MCP Apps proof card

Consumer proof card states:
- Verified
- Not completed
- Awaiting proof

The production resource is `ui://closeloop/proof-card.html`. It is read-only, receives structured
tool results, and fails closed to `Proof unavailable` for contradictory or malformed terminal data.
Evidence and provenance are expandable; the voice-only experience remains complete without the UI.

Verification level: **LOCAL UI/BROWSER VERIFIED** through the official AppBridge transport and
**INTEGRATION VERIFIED** for MCP resource discovery/metadata. It was not rendered by an Alexa+ host.
