# Demo Provider

The executable first-party provider model currently lives in `src/closeloop/demo_provider.py`.

It intentionally supports three deterministic modes:
- healthy
- false_success
- evidence_outage

The provider is intentionally local and deterministic for the recorded demo. No AgentCore Browser
or live subscription-provider integration is implemented or claimed.
