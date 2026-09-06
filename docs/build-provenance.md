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
- Alexa+-compatible self-hosted MCP server with five tools and protected-resource metadata
- Trusted, action-bound confirmation-attestation boundary
- Read-only MCP Apps proof card and local AppBridge validation path
- AWS DynamoDB state/evidence repository and infrastructure template
- Submission-ready demo, judging, verification, friction, and product-feedback evidence

## Reused source

No CUF source code is currently copied into this repository.
