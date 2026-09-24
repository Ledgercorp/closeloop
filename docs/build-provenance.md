# Build Provenance

Hackathon submission period began: **2026-08-31**.

## Prior work / knowledge

The creator previously developed CUF, a broader verification framework centered on evidence-based deterministic outcome semantics including PASS / FAIL / INCONCLUSIVE and the principle that an executing agent should not self-certify success.

## CloseLoop boundary

CloseLoop is a new, consumer-facing Alexa+-specific product. It is not a repackaging of CUF. The hackathon project introduces a new resolution lifecycle, Alexa+ MCP surface, consumer UX, first-party demo provider, fault-injection environment, optional AWS DynamoDB repository, and a specific life-admin workflow.

## Built for this hackathon

- CloseLoop repository and product definition
- Subscription cancellation resolution model
- Independent deterministic cancellation verifier
- First-party demo provider with healthy / false-success / evidence-outage modes
- Consumer state mapping: Verified / Not completed / Awaiting proof
- Fault-injection, lifecycle, protocol, persistence, UI, and adversarial security tests
- Alexa+-compatible self-hosted MCP server (expanded from five to seven tools on 2026-09-24) and protected-resource metadata
- Trusted, action-bound confirmation-attestation boundary
- Read-only MCP Apps proof card and local AppBridge validation path
- AWS DynamoDB state/evidence repository and infrastructure template
- Submission-ready demo, judging, verification, friction, and product-feedback evidence

## Reused source

No CUF source code is currently copied into this repository.

## Persistent resolution evolution (2026-09-24)

This product evolution was implemented in the existing CloseLoop repository and architecture. It adds durable open `AWAITING_PROOF`, bounded read-only rechecks, verification-attempt history, recent-resolution retrieval, an explicit MCP recheck tool, and a simulated later-session public demo. The original deterministic verifier and signed confirmation boundary remain the authority for outcomes and execution. No CUF source was copied; no history was rewritten. Additional resolution kinds are domain-model values only; cancellation is still the only executable workflow. AWS behavior was locally tested with Moto, not a live AWS account; no Alexa+ device/session was used.

## Closed-loop recovery evolution

The closed-loop recovery evolution built on the reconciled persistent-resolution commit. It adds a bounded cancellation `OutcomeContract`, deterministic attention and deduplication, a separate signed-confirmation boundary for simulated recovery actions, recovery provenance, independent reverification, and correlated simulated post-deadline billing evidence. It reuses the existing resolution repository and verifier and does not add an AWS service or copy earlier CUF source. The public `/demo/` exposes only bounded scenario selectors; its provider, billing observations, time progression, and spoken confirmations are simulated. Commit `8af99db73a631821712b7e559ecf335b66ed80a8` was pushed normally to `origin/main`; the existing Vercel Git integration produced deployment `8CxJdnHNEycR3qoxT9YNN6qwQkF9` with successful status at 2026-09-24 18:43:25 UTC. Signed-out Chromium then exercised all five demo scenarios at the canonical production URL. This verifies the simulated demo, not live Alexa+, provider, billing, AWS, or scheduler delivery.
