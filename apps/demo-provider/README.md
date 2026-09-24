# Demo provider

The executable first-party provider model is in `src/closeloop/demo_provider.py`. Its deterministic modes are:

- `healthy`: independent read-back shows auto-renew off and a billing end date.
- `false_success`: provider accepts the request while read-back still shows auto-renew on; CloseLoop keeps the resolution open as `AWAITING_PROOF`.
- `evidence_outage`: independent account evidence is unavailable and the resolution remains open.

The separate `persistent_resolution` public-demo scenario changes simulated evidence after a new service instance resumes the same SQLite-backed record. It uses the real lifecycle and verifier with a deterministic simulated provider. No live subscription-provider, AgentCore, or browser integration is implemented or claimed.
